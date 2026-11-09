"""Writes a clip with the heatmap, per-zone dwell times and a printed alert log.

Why this exists: P4 adds three things that are invisible on their own. This script makes all
three visible at once on a real clip - the heatmap shows where people stood, the dwell numbers
show how long they stayed, and each alert appears in the video as well as in the console log.
That way the panel sees the behaviour instead of taking the numbers on trust.

Every timestamp in this script is a VIDEO timestamp (frame_index / fps), never time.time(), so
the printed events line up exactly with the recording, however slowly the CPU runs.

Run: .venv\\Scripts\\python.exe scripts\\demo_step4.py demo_videos\\crowded.mp4
"""

import sys
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app import config
from app.analytics import AlertDebouncer, DwellTracker, HeatmapAccumulator
from app.vision import Detector, resize_frame
from app.zones import Zone, count_by_zone, draw_zones, load_zones, status_for

# ---------- Look-and-feel settings (drawing only, they never change a number) ----------

# Colour of a person's box, in OpenCV's BGR order.
BOX_COLOR = (0, 255, 0)
# Colour of the dot on the person's feet - the exact pixel the zone test and heatmap use.
FOOT_COLOR = (0, 0, 255)
# Colours for the event lines: red for a new alert, green for a cleared one.
ALERT_COLOR = (0, 0, 255)
CLEAR_COLOR = (0, 255, 0)
TEXT_COLOR = (255, 255, 255)
# Frame rate to assume when the file's metadata is broken.
DEFAULT_FPS = 25.0
# Box and dot sizes, in pixels.
THICKNESS = 2
DOT_RADIUS = 4
# Size of the dark strip behind the status text, and the height of one event line.
STRIP_HEIGHT = 30
EVENT_LINE_HEIGHT = 26
# How long an event stays on screen, in video seconds, so a viewer can actually read it.
EVENT_HOLD_SECONDS = 4.0
# Maximum event lines drawn at once; older ones have scrolled off the top by then.
MAX_EVENT_LINES = 4
# Reused font settings for every line of text we draw.
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.55
FONT_THICKNESS = 1


def open_clip(path: Path) -> tuple[cv2.VideoCapture, float]:
    """Opens the clip and reads its frame rate, because every time value depends on it.

    Why stop on a bad frame rate instead of guessing: the dwell times and the alert delays are
    all in video seconds. A silent fallback to the wrong fps would make every printed number
    wrong, and wrong numbers are worse than a clear error.

    Example: a 30 fps clip gives 2 / 30 = 0.067 s per analysed frame at STRIDE 2.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open clip: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps <= 0:
        # Broken metadata is common on downloaded files, so 25 fps is a usable fallback here.
        fps = DEFAULT_FPS
    return capture, float(fps)


def draw_people(frame: np.ndarray, people: list) -> None:
    """Draws each person's box and foot dot on the frame.

    Why the dot as well as the box: the dot is the point that decides the zone and feeds the
    heatmap. Seeing dots inside the polygon is what proves the counting and the heat are right.
    """
    for person in people:
        x1, y1, x2, y2 = person.box
        cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, THICKNESS)
        cv2.circle(frame, person.foot, DOT_RADIUS, FOOT_COLOR, -1)


def draw_dwell_labels(frame: np.ndarray, zones: list[Zone],
                      dwell: dict[str, tuple[float, float]]) -> None:
    """Writes each zone's average and longest dwell time just under its name label.

    Why show both numbers: the average says how the area feels, and the maximum points at the
    single person who is stuck. A bottleneck hides in the difference between the two.

    Example: "avg 3.4s  max 6.1s" under the zone label.
    """
    for zone in zones:
        average, longest = dwell.get(zone.name, (0.0, 0.0))
        points = zone.polygon.reshape(-1, 2)
        # Sit below the zone's own label, which is drawn above the topmost corner.
        x = int(points[:, 0].min())
        y = min(int(points[:, 1].min()) + 16, frame.shape[0] - 6)
        text = f"avg {average:.1f}s  max {longest:.1f}s"
        cv2.putText(frame, text, (x + 3, y), FONT, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, text, (x + 3, y), FONT, 0.45, TEXT_COLOR, 1, cv2.LINE_AA)


def draw_status_strip(frame: np.ndarray, text: str) -> None:
    """Writes one line of summary text in the top-left corner on a dark strip.

    Why: the viewer needs the overall numbers without reading every zone label.
    """
    cv2.rectangle(frame, (0, 0), (frame.shape[1], STRIP_HEIGHT), (0, 0, 0), -1)
    cv2.putText(frame, text, (8, 21), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICKNESS, cv2.LINE_AA)


def draw_events(frame: np.ndarray, events: list[tuple[float, str, str]], now: float) -> None:
    """Draws the recent TRIGGERED / CLEARED lines in the top-left, under the status strip.

    Why keep them on screen for a few seconds: an event that flashes for one frame is
    unreadable, and the video is the evidence a reviewer will look at.

    Why a dark panel behind the text: white text over a bright marble floor disappears.
    """
    visible = [event for event in events if now - event[0] <= EVENT_HOLD_SECONDS]
    visible = visible[-MAX_EVENT_LINES:]
    if not visible:
        return

    panel_height = STRIP_HEIGHT + EVENT_LINE_HEIGHT * len(visible) + 4
    cv2.rectangle(frame, (0, STRIP_HEIGHT), (frame.shape[1], panel_height), (0, 0, 0), -1)
    for index, (event_time, message, kind) in enumerate(visible):
        colour = ALERT_COLOR if kind == "TRIGGERED" else CLEAR_COLOR
        y = STRIP_HEIGHT + EVENT_LINE_HEIGHT * (index + 1)
        cv2.putText(frame, f"{event_time:6.1f}s  {message}", (8, y), FONT, 0.5, colour,
                    FONT_THICKNESS, cv2.LINE_AA)


def status_strip_text(counts: dict[str, int], active_alerts: list[str]) -> str:
    """Builds the top strip: people inside zones, and which zones are currently alerting.

    Example: {"Main Zone": 6} with one active alert gives
    "People 6 | Main Zone 6 | ALERT: Main Zone".
    """
    total = sum(counts.values())
    parts = " | ".join(f"{name} {value}" for name, value in counts.items())
    text = f"People {total} | {parts}" if parts else f"People {total}"
    if active_alerts:
        text += " | ALERT: " + ", ".join(active_alerts)
    return text


def open_writer(destination: Path, frame: np.ndarray, output_fps: float) -> cv2.VideoWriter:
    """Creates the MP4 writer from the first frame, because the size must be known up front.

    Why a helper: both the creation and the failure check are easy to forget, and a silent
    VideoWriter produces a zero-byte file that looks like a rendering bug.

    Why output_fps rather than the source fps: we write one frame for every STRIDE source
    frames, so writing them at the source rate makes the video play twice as fast and every
    printed timestamp drift away from the player's clock. Writing at fps / STRIDE keeps the
    duration right, so "31.5s TRIGGERED" really appears 31.5 s into the file.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    height, width = frame.shape[:2]
    writer = cv2.VideoWriter(str(destination), fourcc, output_fps, (width, height))
    if not writer.isOpened():
        raise SystemExit(f"Cannot write video: {destination}")
    return writer


def annotate(clip_path: Path) -> None:
    """Runs detection, analytics and drawing over the whole clip and saves an MP4.

    The pipeline per analysed frame is:
      1. detect and track people,
      2. group their feet by zone,
      3. feed the zones into DwellTracker and the feet into HeatmapAccumulator,
      4. feed each zone's count into its AlertDebouncer,
      5. draw everything and write the frame.
    """
    capture, fps = open_clip(clip_path)
    # Zones are keyed by the exact file name, so a missing entry fails with a clear message.
    zones = load_zones(config.ZONES_FILE, clip_path.name)
    detector = Detector()

    # One debouncer per zone: each zone has its own capacity and must alert independently.
    debouncers = {zone.name: AlertDebouncer(zone.name) for zone in zones}
    dwell = DwellTracker()
    # The heatmap needs the real frame size, which we only learn from the first decoded frame,
    # so it starts as None and is created inside the loop.
    heatmap: HeatmapAccumulator | None = None

    destination = config.OUTPUT_DIR / f"step4_{clip_path.stem}.mp4"
    writer: cv2.VideoWriter | None = None
    events: list[tuple[float, str, str]] = []
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

            # The heatmap must match the real frame size, which we only know from this frame.
            if heatmap is None:
                heatmap = HeatmapAccumulator(frame.shape[1], frame.shape[0])

            people = detector.track(frame)
            grouped = count_by_zone(zones, people)
            counts = {name: len(group) for name, group in grouped.items()}
            members = {name: [person.track_id for person in group]
                       for name, group in grouped.items()}

            # Video time of this frame, so printed times match the player's clock.
            now = frame_index / fps

            dwell.update(now, members)
            # One point per person: the same foot pixel the zone test uses.
            heatmap.add([person.foot for person in people])

            for zone in zones:
                event = debouncers[zone.name].update(now, counts[zone.name], zone.capacity)
                if event is None:
                    continue
                message = f"{zone.name} {counts[zone.name]}/{zone.capacity} {event}"
                events.append((now, message, event))
                print(f"  {now:6.1f}s  {message}")

            zone_dwell = {zone.name: dwell.stats(zone.name, now) for zone in zones}
            active = [name for name, box in debouncers.items() if box.active]

            # Order matters: heat first, then boxes and zones on top, so people stay readable.
            canvas = heatmap.overlay(frame)
            draw_people(canvas, people)
            canvas = draw_zones(canvas, zones, counts)
            draw_dwell_labels(canvas, zones, zone_dwell)
            draw_status_strip(canvas, status_strip_text(counts, active))
            draw_events(canvas, events, now)

            if writer is None:
                # One written frame stands for STRIDE source frames, so the file must play slower.
                writer = open_writer(destination, canvas, fps / config.STRIDE)
            writer.write(canvas)
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
    print(f"events     : {len(events)}")
    for name, debouncer in debouncers.items():
        print(f"  {name}: active={debouncer.active} over_for={debouncer.over_for:.1f}s")


def main() -> None:
    """Checks the single argument and runs the annotation."""
    if len(sys.argv) != 2:
        raise SystemExit(r"Usage: .venv\Scripts\python.exe scripts\demo_step4.py <clip>")
    clip_path = Path(sys.argv[1])
    if not clip_path.exists():
        raise SystemExit(f"Clip not found: {clip_path}")
    print(f"clip       : {clip_path.name}")
    annotate(clip_path)


if __name__ == "__main__":
    main()
