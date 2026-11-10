"""Owns the zones: their polygons, their capacities and which zone a person stands in.

Why this file exists: the dashboard, the counting and the alerts all ask one question -
"which zone is this person standing in, and is that zone full?" - and they must all get the
same answer. Keeping the geometry and the status rule in one small module means the answer
cannot drift between the video demo, the API and the tests.

Coordinates inside a Zone are in the RESIZED frame (config.FRAME_WIDTH pixels wide), because
that is the frame YOLO sees, so foot points and polygons use the same units. Zones are stored
per clip in zones.json, because every clip has a different camera view.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app import config
from app.vision import Person


@dataclass
class Zone:
    """One area of the picture with a name and a comfortable capacity.

    The polygon is a numpy array shaped (N, 1, 2) of int32 values, because that is the exact
    format cv2.pointPolygonTest and cv2.fillPoly expect. Keeping the conversion here means no
    other file has to remember it.
    """

    name: str
    capacity: int
    polygon: np.ndarray

    def points(self) -> list[tuple[int, int]]:
        """Returns the polygon as a plain list of (x, y) pairs, the shape zones.json stores.

        Why: saving to JSON needs plain numbers, not a numpy array, and the shape (N, 1, 2)
        would otherwise be written as nested one-item lists.
        """
        return [(int(x), int(y)) for x, y in self.polygon.reshape(-1, 2)]


def make_polygon(points: list[tuple[int, int]]) -> np.ndarray:
    """Turns [(x, y), ...] into the (N, 1, 2) int32 array OpenCV wants.

    Why: a zone is written in JSON as a readable list of points, but OpenCV needs a specific
    array layout. One conversion function keeps that detail in one place.

    Example: [(10, 10), (20, 10), (20, 20)] becomes an array with shape (3, 1, 2).
    """
    return np.array(points, dtype=np.int32).reshape(-1, 1, 2)


def load_zones(path: Path, source_name: str) -> list[Zone]:
    """Reads the zones for one clip out of zones.json.

    Why: zones belong to a camera view, so loading them by clip name stops a polygon drawn
    for one video from being used on another. A clip with no entry is an error we explain,
    because silently drawing no zones would look like "nobody is ever in a zone".
    """
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Zones file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        # An empty file is a common half-finished state, so treat it like "{}".
        text = handle.read().strip() or "{}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Zones file is not valid JSON: {path} ({error})") from error

    if source_name not in data:
        raise SystemExit(
            f"No zones for clip '{source_name}' in {path}.\n"
            f"Add an entry named \"{source_name}\" to that file first."
        )

    zones: list[Zone] = []
    for entry in data[source_name]:
        zones.append(
            Zone(
                name=str(entry["name"]),
                capacity=int(entry["capacity"]),
                polygon=make_polygon([(int(x), int(y)) for x, y in entry["polygon"]]),
            )
        )
    return zones


def zone_of(zones: list[Zone], point: tuple[int, int]) -> Zone | None:
    """Returns the first zone that contains this point, or None.

    Why: a foot point can only be in one place, but polygons can overlap. "First match wins"
    is a simple, predictable rule, and zones.json lists the most important zone first.

    measureDist=False means we only ask "inside or not" and get a value >= 0 for inside and
    on the edge, < 0 for outside. That is faster than asking for the real distance.
    """
    for zone in zones:
        # OpenCV needs the point as a float tuple; our points are whole pixels.
        inside = cv2.pointPolygonTest(zone.polygon, (float(point[0]), float(point[1])), False)
        if inside >= 0:
            return zone
    return None


def count_by_zone(zones: list[Zone], people: list[Person]) -> dict[str, list[Person]]:
    """Groups people by the zone their feet are standing in.

    Why: every zone needs its own list, including zones with nobody in them, so the dashboard
    can show "0 / 5" instead of hiding a zone that just became empty.

    Example: feet at (100, 200) inside "Main Zone" and (600, 40) outside every zone give
    {"Main Zone": [person1]} - person2 is in no list, because they are in no zone.
    """
    # Start every zone at an empty list so empty zones still appear in the result.
    counted: dict[str, list[Person]] = {zone.name: [] for zone in zones}
    for person in people:
        zone = zone_of(zones, person.foot)
        if zone is not None:
            counted[zone.name].append(person)
    return counted


def status_for(count: int, capacity: int) -> str:
    """Turns a head count and a capacity into the status word the UI shows.

    Why: one rule, used by the video demo, the API and the tests, so the colours and the
    alert logic can never disagree.

    "NEAR" starts at NEAR_RATIO (0.8) of capacity, so people see a warning before it is full.
    "OVER" is strictly more than capacity: exactly full is still NEAR, not OVER.

    Example with capacity 10: 7 -> OK, 8 -> NEAR, 10 -> NEAR, 11 -> OVER.
    """
    if count > capacity:
        return "OVER"
    if count >= config.NEAR_RATIO * capacity:
        return "NEAR"
    return "OK"


# Fill colours (BGR) for the three statuses. Kept here, not in config, because they are
# drawing choices for this module only and never affect a number.
STATUS_COLORS = {
    "OK": (0, 180, 0),      # green
    "NEAR": (0, 170, 255),  # amber
    "OVER": (0, 0, 220),    # red
}
# How much of the fill colour survives on top of the video, so people stay visible.
FILL_ALPHA = 0.25
# Outline thickness and label size, in pixels / OpenCV font units.
OUTLINE_THICKNESS = 2
LABEL_SCALE = 0.55


def draw_zones(frame: np.ndarray, zones: list[Zone], counts: dict[str, int]) -> np.ndarray:
    """Draws every zone on a copy of the frame: translucent fill, outline and a label.

    Why a copy: the caller keeps the clean frame for detection, and drawing on the original
    would slowly paint boxes into the video we measure.

    The colours come from status_for, so a zone turns amber before it is full and red once it
    is over - the same rule the alert uses.

    Example: "Main Zone 6/5" is drawn red, because 6 > 5.
    """
    canvas = frame.copy()
    for zone in zones:
        count = counts.get(zone.name, 0)
        status = status_for(count, zone.capacity)
        color = STATUS_COLORS[status]

        # A separate overlay layer lets us blend the fill without darkening the outline.
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [zone.polygon], color)
        cv2.addWeighted(overlay, FILL_ALPHA, canvas, 1 - FILL_ALPHA, 0, canvas)
        cv2.polylines(canvas, [zone.polygon], True, color, OUTLINE_THICKNESS)

        label = f"{zone.name}  {count}/{zone.capacity}"
        _draw_label(canvas, zone, label, color)
    return canvas


def _draw_label(frame: np.ndarray, zone: Zone, text: str, color: tuple[int, int, int]) -> None:
    """Writes the zone label near the top of its polygon, on a dark strip so it stays readable.

    Why near the top: the label must not cover the people we are counting, and the top edge is
    usually the emptiest part of the area (the far side of the floor).
    """
    points = zone.polygon.reshape(-1, 2)
    # Place the text just above the highest corner, so it never sits inside the crowd.
    x = int(points[:, 0].min())
    y = max(int(points[:, 1].min()) - 8, 14)
    (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                                          LABEL_SCALE, 1)
    cv2.rectangle(frame, (x, y - text_height - 4),
                  (x + text_width + 6, y + baseline), (0, 0, 0), -1)
    cv2.putText(frame, text, (x + 3, y), cv2.FONT_HERSHEY_SIMPLEX, LABEL_SCALE, color, 1,
                cv2.LINE_AA)


def _format_zone(entry: dict) -> str:
    """Formats one saved zone as JSON with each [x, y] point on a single line.

    Why not plain json.dumps: with indent=2 every coordinate gets its own line, so an 8-corner
    zone becomes 48 lines of numbers that nobody can read or review. This keeps the file tidy
    enough to show on a projector.

    Example output:
        {
          "name": "Main Zone",
          "capacity": 4,
          "polygon": [[284, 232], [300, 274], [352, 309]]
        }
    """
    points = ", ".join(f"[{int(x)}, {int(y)}]" for x, y in entry["polygon"])
    return (
        "    {\n"
        f'      "name": "{entry["name"]}",\n'
        f'      "capacity": {int(entry["capacity"])},\n'
        f'      "polygon": [{points}]\n'
        "    }"
    )


def save_zones(path: Path, source_name: str, zones: list[Zone]) -> None:
    """Writes (or replaces) the entry for one clip, keeping every other clip's zones.

    Why merge instead of overwrite: zones.json holds all three clips. Generating zones for
    one clip must not wipe the work done for the others.

    Example: a file with only "normal.mp4" gains "mid.mp4" and keeps both.
    """
    path = Path(path)
    data: dict[str, list[dict]] = {}
    if path.exists():
        text = path.read_text(encoding="utf-8").strip() or "{}"
        data = json.loads(text)

    data[source_name] = [
        {"name": zone.name, "capacity": zone.capacity, "polygon": zone.points()}
        for zone in zones
    ]

    # Sort clip names so the file order is stable, which keeps git diffs small.
    blocks = []
    for clip_name in sorted(data):
        zone_blocks = ",\n".join(_format_zone(entry) for entry in data[clip_name])
        blocks.append(f'  "{clip_name}": [\n{zone_blocks}\n  ]')
    path.write_text("{\n" + ",\n".join(blocks) + "\n}\n", encoding="utf-8")
