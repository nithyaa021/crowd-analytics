"""Writes an annotated copy of a clip: boxes, zones, live counts and status colours.

Why this exists: P3 must be something you can watch. It proves three things at once -
the zone polygon is in the right place, the count inside it changes as people walk,
and the colour follows the OK / NEAR / OVER rule from app/zones.py.

It also prints one line every time a zone's status changes, with the video time, so you can
check the printed log against the video instead of trusting it.

Run: .venv\\Scripts\\python.exe scripts\\demo_step3.py demo_videos\\crowded.mp4
"""

import sys
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app import config
from app.vision import Detector, resize_frame
from app.zones import Zone, count_by_zone, draw_zones, load_zones, status_for

# ---------- Look-and-feel settings (drawing only, they never change a count) ----------

# Colour of a person's box, in OpenCV's BGR order.
BOX_COLOR = (0, 255, 0)
# Colour of the dot on the person's feet.
FOOT_COLOR = (0, 0, 255)
# Colour of the status strip text.
TEXT_COLOR = (255, 255, 255)
# Frame rate to assume when the file's metadata is broken.
DEFAULT_FPS = 25.0
# Box and dot sizes, in pixels.
THICKNESS = 2
DOT_RADIUS = 4
# Size of the black strip behind the status text.
STATUS_BOX_WIDTH = 420
STATUS_BOX_HEIGHT = 30


def open_clip(path: Path) -> tuple[cv2.VideoCapture, float]:
    """Opens the clip and reads its frame rate, so printed times match the real video.

    Why: every printed status line carries a video time. A wrong frame rate would make all of
    those times wrong, which is worse than stopping.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open clip: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps <= 0:
        # Broken metadata is common on downloaded files; 25 fps still gives usable timings.
        fps = DEFAULT_FPS
    return capture, float(fps)


def draw_people(frame: np.ndarray, people: list) -> None:
    """Draws each person's box and foot dot on the frame.

    Why: the foot dot is the exact point the zone test uses, so seeing the dots inside the
    polygon is the visual proof that counting works.
    """
    for person in people:
        x1, y1, x2, y2 = person.box
        cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, THICKNESS)
        cv2.circle(frame, person.foot, DOT_RADIUS, FOOT_COLOR, -1)


def draw_status_strip(frame: np.ndarray, text: str) -> None:
    """Writes the overall status line in the top-left corner on a dark strip.

    Why: one glance should tell the viewer how busy the whole frame is, without reading the
    zone labels one by one.
    """
    cv2.rectangle(frame, (0, 0), (STATUS_BOX_WIDTH, STATUS_BOX_HEIGHT), (0, 0, 0), -1)
    cv2.putText(frame, text, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TEXT_COLOR, 1, cv2.LINE_AA)


def total_text(counts: dict[str, int]) -> str:
    """Builds the strip text: total people and each zone's own count.

    Example: {"Main Zone": 7} -> "People 7 | Main Zone 7".
    """
    total = sum(counts.values())
    parts = " | ".join(f"{name} {value}" for name, value in counts.items())
    return f"People {total} | {parts}" if parts else f"People {total}"


def print_changes(previous: dict[str, str], counts: dict[str, int], zones: list[Zone],
                  video_seconds: float) -> None:
    """Prints a line for every zone whose status changed since the last processed frame.

    Why: the video shows the colour, this log gives the timestamp. Together they are the proof
    that the alert rule fires at the right moment, and they are easy to quote in the review.

    Example: "  12.4s  Main Zone  8/5  NEAR -> OVER".
    """
    for zone in zones:
        count = counts.get(zone.name, 0)
        status = status_for(count, zone.capacity)
        old = previous.get(zone.name)
        if old is None:
            # The first frame explains what we start from instead of pretending nothing changed.
            print(f"  {video_seconds:6.1f}s  {zone.name}  {count}/{zone.capacity}  start {status}")
        elif status != old:
            print(f"  {video_seconds:6.1f}s  {zone.name}  {count}/{zone.capacity}  {old} -> {status}")
        previous[zone.name] = status


def annotate(clip_path: Path) -> None:
    """Runs detection, counting and zone drawing over the whole clip and saves an MP4."""
    capture, fps = open_clip(clip_path)
    # Zones are keyed by the exact file name, so this fails clearly if they were never built.
    zones = load_zones(config.ZONES_FILE, clip_path.name)
    detector = Detector()

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    destination = config.OUTPUT_DIR / f"step3_{clip_path.stem}.mp4"
    writer: cv2.VideoWriter | None = None
    previous: dict[str, str] = {}
    frame_index = 0
    written = 0

    while True:
        # grab() advances cheaply; only every STRIDE-th frame is decoded and analysed.
        if not capture.grab():
            break
        if frame_index % config.STRIDE == 0:
            ok, frame = capture.retrieve()
            if not ok:
                break
            frame = resize_frame(frame, config.FRAME_WIDTH)

            people = detector.track(frame)
            grouped = count_by_zone(zones, people)
            counts = {name: len(group) for name, group in grouped.items()}

            # Video time of this frame, so the printed log can be checked against the player.
            video_seconds = frame_index / fps
            print_changes(previous, counts, zones, video_seconds)

            draw_people(frame, people)
            frame = draw_zones(frame, zones, counts)
            draw_status_strip(frame, total_text(counts))

            if writer is None:
                height, width = frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(destination), fourcc, fps, (width, height))
                if not writer.isOpened():
                    raise SystemExit(f"Cannot write video: {destination}")
            writer.write(frame)
            written += 1
        frame_index += 1

    capture.release()
    if writer is not None:
        writer.release()
    if written == 0:
        raise SystemExit(f"No frames were analysed from: {clip_path}")

    print(f"output     : {destination}")
    print(f"frames     : {written}")
    print(f"video time : {written * config.STRIDE / fps:.1f}s")
    print(f"zones      : " + ", ".join(f"{z.name} capacity {z.capacity}" for z in zones))


def main() -> None:
    """Checks the single argument and runs the annotation."""
    if len(sys.argv) != 2:
        raise SystemExit(r"Usage: .venv\Scripts\python.exe scripts\demo_step3.py <clip>")
    clip_path = Path(sys.argv[1])
    if not clip_path.exists():
        raise SystemExit(f"Clip not found: {clip_path}")
    annotate(clip_path)


if __name__ == "__main__":
    main()
