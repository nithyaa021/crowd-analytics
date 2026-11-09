"""Writes an annotated copy of a video: boxes, tracking IDs and foot points.

Why: step P1 must be something you can watch, not just a list of numbers, so this script
saves a labelled MP4 that plays in any video player on Windows.

Run: .venv\\Scripts\\python.exe scripts\\demo_step1.py demo_videos\\your_clip.mp4
"""

import math
import sys
import time
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app import config
from app.vision import Detector, Person, resize_frame

# ---------- Look-and-feel settings (they never change detection results) ----------

# Colour of a person's box, in OpenCV's BGR order (not RGB).
BOX_COLOR = (0, 255, 0)
# Colour of the dot on the person's feet.
FOOT_COLOR = (0, 0, 255)
# Colour of all text drawn on the frame.
TEXT_COLOR = (255, 255, 255)
# Colour of the strip behind the status text, so it stays readable on bright video.
STATUS_BG_COLOR = (0, 0, 0)
# Line width for boxes and text.
THICKNESS = 2
# OpenCV's simple built-in font.
FONT = cv2.FONT_HERSHEY_SIMPLEX
# Text height scale; 0.55 is readable at 640 pixels wide.
FONT_SCALE = 0.55
# Radius of the foot dot, in pixels.
DOT_RADIUS = 4
# Frame rate to use when a video's metadata is missing or broken.
DEFAULT_FPS = 25.0
# Size of the black rectangle behind the status text, in pixels.
STATUS_BOX_WIDTH = 300
STATUS_BOX_HEIGHT = 32


def open_video(path: Path) -> cv2.VideoCapture:
    """Opens the video and stops with a clear message if OpenCV cannot read it."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open video: {path}")
    return capture


def source_fps(capture: cv2.VideoCapture) -> float:
    """Reads the video's own frame rate so the saved clip plays at the original speed."""
    fps = capture.get(cv2.CAP_PROP_FPS)
    # Broken metadata can report 0 or nan; fall back to a common 25 fps.
    return fps if math.isfinite(fps) and fps > 0 else DEFAULT_FPS


def make_writer(path: Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    """Creates an MP4 writer using the codec Windows OpenCV already supports."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise SystemExit(f"Cannot write video: {path}")
    return writer


def draw_person(frame: np.ndarray, person: Person) -> None:
    """Draws one person's box, ID label and foot dot directly on the frame."""
    x1, y1, x2, y2 = person.box
    cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, THICKNESS)
    # The label sits above the box; max() stops it from disappearing off the top edge.
    label = f"#{person.track_id} {person.conf:.2f}"
    cv2.putText(
        frame, label, (x1, max(y1 - 6, 12)), FONT, FONT_SCALE, TEXT_COLOR, 1, cv2.LINE_AA
    )
    # A filled circle marks the foot point that the zones will test later.
    cv2.circle(frame, person.foot, DOT_RADIUS, FOOT_COLOR, -1)


def draw_status(frame: np.ndarray, fps: float, people_count: int) -> None:
    """Writes the running FPS and the number of people onto the top-left corner."""
    text = f"FPS {fps:5.1f} | People {people_count}"
    # A dark strip keeps white text readable over both bright and dark footage.
    cv2.rectangle(frame, (0, 0), (STATUS_BOX_WIDTH, STATUS_BOX_HEIGHT), STATUS_BG_COLOR, -1)
    cv2.putText(
        frame, text, (8, 22), FONT, 0.6, TEXT_COLOR, 1, cv2.LINE_AA
    )


def print_summary(output_path: Path, frames: int, fps: float, people: float, ids: int) -> None:
    """Prints the four facts the step asks for, in a format that is easy to read aloud."""
    print(f"output       : {output_path}")
    print(f"frames       : {frames}")
    print(f"avg FPS      : {fps:.1f}")
    print(f"avg people   : {people:.2f}")
    print(f"unique IDs   : {ids}")


def annotate_video(video_path: Path) -> None:
    """Runs detection and tracking over the whole video and saves an annotated copy."""
    capture = open_video(video_path)
    fps_in = source_fps(capture)
    detector = Detector()
    output_path = config.OUTPUT_DIR / f"step1_{video_path.stem}.mp4"
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    writer: cv2.VideoWriter | None = None
    frame_index = 0
    frames_processed = 0
    people_total = 0
    unique_ids: set[int] = set()
    started = time.perf_counter()

    while True:
        # grab() advances one frame without decoding it: the cheap way to skip frames.
        if not capture.grab():
            break
        # STRIDE=2 means frames 0, 2, 4 ... are analysed; odd frames are only grabbed.
        if frame_index % config.STRIDE == 0:
            ok, frame = capture.retrieve()
            if not ok:
                break
            frame = resize_frame(frame, config.FRAME_WIDTH)
            # The writer needs the frame size, so create it from the first resized frame.
            if writer is None:
                height, width = frame.shape[:2]
                writer = make_writer(output_path, fps_in, width, height)

            people = detector.track(frame)
            for person in people:
                draw_person(frame, person)
            # Running FPS = frames finished so far divided by seconds spent so far.
            running_fps = frames_processed / max(time.perf_counter() - started, 1e-6)
            draw_status(frame, running_fps, len(people))
            writer.write(frame)

            frames_processed += 1
            people_total += len(people)
            unique_ids.update(person.track_id for person in people)
        frame_index += 1

    capture.release()
    if writer is not None:
        writer.release()

    if frames_processed == 0:
        raise SystemExit(f"No frames could be read from: {video_path}")

    elapsed = time.perf_counter() - started
    print_summary(
        output_path,
        frames_processed,
        frames_processed / elapsed,
        people_total / frames_processed,
        len(unique_ids),
    )


def main() -> None:
    """Checks the single command-line argument, then runs the annotation."""
    if len(sys.argv) != 2:
        raise SystemExit(r"Usage: .venv\Scripts\python.exe scripts\demo_step1.py <video>")
    video_path = Path(sys.argv[1])
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")
    annotate_video(video_path)


if __name__ == "__main__":
    main()
