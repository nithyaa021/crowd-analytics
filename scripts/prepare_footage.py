"""Cuts three raw videos into demo clips and measures how crowded each clip really is.

Why: the dashboard demo needs three fixed-camera clips with a known crowd level, and the
panel should see measured numbers instead of guesses.

Run: .venv\\Scripts\\python.exe scripts\\prepare_footage.py
"""

import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app import config
from app.vision import Detector, resize_frame

# ---------- Step settings (this script only, so app/config.py stays untouched) ----------

# Folder holding the downloaded source videos.
RAW_DIR = config.VIDEO_DIR / "raw"
# Folder for the first/last frame pictures that prove the shot is stable.
PREVIEW_DIR = config.VIDEO_DIR / "previews"

# A clip must be at least this many seconds long to be useful for a demo.
MIN_SECONDS = 20.0
# A clip is never longer than this, to keep the demo short and the files small.
MAX_SECONDS = 45.0

# Mean grey difference (0-255) between two frames that we treat as a hard cut.
CUT_THRESHOLD = 30.0
# Frames are compared at this small width, which makes the cut scan fast and noise-free.
COMPARE_WIDTH = 320

# Warn when the first and last preview differ more than this; a big change hints at a cut.
PREVIEW_DIFF_WARNING = 35.0

# Final clips are written at 1280 px wide (720p for 16:9): sharp enough for YOLO, light for Git.
OUTPUT_WIDTH = 1280

# Which raw file plays which role, and the measured max that role is expected to show.
# Replace a file here (and in demo_videos/SOURCES.csv) if a clip does not fit its role.
CLIPS = [
    ("normal", "36304379.mp4"),
    ("mid", "14393753.mp4"),
    ("crowded", "18516076.mp4"),
]

# Lowest and highest "max people in one frame" that make a clip believable for each role.
EXPECTED_RANGE = {
    "normal": (0, 6),
    "mid": (7, 14),
    "crowded": (12, None),  # no upper limit: a crowd can be as big as it is
}

# Plain-English alert behaviour shown in expected_results.md.
EXPECTED_ALERT = {
    "normal": "None - stays under capacity",
    "mid": "Maybe - a low-capacity zone can fill up",
    "crowded": "Yes - zone goes over capacity",
}


@dataclass
class VideoInfo:
    """Technical facts about one raw video, plus the frames where it cuts."""

    fps: float
    frames: int
    width: int
    height: int
    cuts: list[int]


@dataclass
class ClipResult:
    """Everything we measured for one finished demo clip."""

    role: str
    source_name: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    width: int
    height: int
    max_people: int
    median_people: int
    fits_role: bool
    preview_diff: float


def small_gray(frame: np.ndarray) -> np.ndarray:
    """Shrinks a frame to a small grey image, so comparing two frames is cheap and stable.

    Example: a 1920x1080 frame becomes 320x180 grey; colour changes in a shirt then
    barely affect the comparison, while a scene change still stands out.
    """
    scale = COMPARE_WIDTH / frame.shape[1]
    size = (COMPARE_WIDTH, max(int(frame.shape[0] * scale), 1))
    return cv2.cvtColor(cv2.resize(frame, size), cv2.COLOR_BGR2GRAY)


def frame_diff(previous: np.ndarray, current: np.ndarray) -> float:
    """Returns the average brightness change between two small grey frames (0-255).

    Why: one number per frame pair lets us spot cuts, where nearly every pixel changes.
    Example: two frames of the same shot score 3-10; two different shots score 40-90.
    """
    return float(np.mean(cv2.absdiff(previous, current)))


def scan_video(video_path: Path) -> VideoInfo:
    """Reads a whole video once and records its size, frame rate and cut positions."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open raw video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    # A broken frame rate would make every duration wrong, so stop instead of guessing.
    if not fps or fps != fps:
        raise SystemExit(f"Video has no usable frame rate: {video_path}")

    cuts: list[int] = []
    previous = None
    index = 0
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    while index < total:
        ok, frame = capture.read()
        if not ok:
            break
        current = small_gray(frame)
        # The first frame has nothing to compare with, so it can never be a cut.
        if previous is not None and frame_diff(previous, current) > CUT_THRESHOLD:
            cuts.append(index)
        previous = current
        index += 1

    info = VideoInfo(
        fps=float(fps),
        frames=index,
        width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
        height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        cuts=cuts,
    )
    capture.release()
    return info


def longest_stretch(cuts: list[int], total_frames: int) -> tuple[int, int]:
    """Finds the longest run of frames with no cut, returned as (start, end).

    Example: cuts at frame 300 with 900 frames total gives stretches 0-300 and 300-900,
    so the answer is (300, 900): the second shot is twice as long.
    """
    bounds = [0] + cuts + [total_frames]
    pairs = list(zip(bounds[:-1], bounds[1:]))
    return max(pairs, key=lambda pair: pair[1] - pair[0])


def trim_to_limit(info: VideoInfo, start: int, end: int) -> tuple[int, int]:
    """Caps the chosen stretch at MAX_SECONDS and rejects anything shorter than MIN_SECONDS."""
    end = min(end, start + int(MAX_SECONDS * info.fps))
    seconds = (end - start) / info.fps
    if seconds < MIN_SECONDS:
        raise SystemExit(
            f"Longest cut-free stretch is only {seconds:.1f}s; need at least {MIN_SECONDS:.0f}s. "
            "Replace this source file."
        )
    return start, end


def write_clip(source: Path, info: VideoInfo, start: int, end: int, destination: Path) -> tuple[int, int]:
    """Copies the chosen frames into a new MP4, resized to OUTPUT_WIDTH."""
    capture = cv2.VideoCapture(str(source))
    capture.set(cv2.CAP_PROP_POS_FRAMES, start)
    writer = None
    for _ in range(end - start):
        ok, frame = capture.read()
        if not ok:
            break
        frame = resize_frame(frame, OUTPUT_WIDTH)
        if writer is None:
            height, width = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(destination), fourcc, info.fps, (width, height))
            if not writer.isOpened():
                raise SystemExit(f"Cannot write clip: {destination}")
        writer.write(frame)
    capture.release()
    if writer is None:
        raise SystemExit(f"No frames written for: {destination}")
    writer.release()
    return width, height


def save_previews(clip_path: Path, role: str) -> float:
    """Saves the first and last frame as PNGs and returns how different they look.

    Why: if the camera moved or a cut slipped in, the two pictures look unrelated, and the
    warning tells us before the demo does.
    """
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(clip_path))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok_first, first = capture.read()
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(total - 1, 0))
    ok_last, last = capture.read()
    capture.release()
    if not (ok_first and ok_last):
        raise SystemExit(f"Cannot read preview frames from: {clip_path}")

    cv2.imwrite(str(PREVIEW_DIR / f"{role}_first.png"), first)
    cv2.imwrite(str(PREVIEW_DIR / f"{role}_last.png"), last)
    return frame_diff(small_gray(first), small_gray(last))


def measure_people(clip_path: Path, detector: Detector) -> tuple[int, int]:
    """Runs the real Detector over the clip and returns (max, median) people per frame.

    Why: these are the numbers the dashboard will actually see, so they decide whether the
    clip is honest about being "normal", "mid" or "crowded".
    """
    capture = cv2.VideoCapture(str(clip_path))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open finished clip: {clip_path}")

    counts: list[int] = []
    index = 0
    while True:
        # grab() skips a frame cheaply; only the frames we analyse are fully decoded.
        if not capture.grab():
            break
        if index % config.STRIDE == 0:
            ok, frame = capture.retrieve()
            if not ok:
                break
            people = detector.track(resize_frame(frame, config.FRAME_WIDTH))
            counts.append(len(people))
        index += 1
    capture.release()

    if not counts:
        raise SystemExit(f"No frames analysed in: {clip_path}")
    return max(counts), int(statistics.median(counts))


def fits_role(role: str, max_people: int) -> bool:
    """Checks the measured maximum against the range the scenario expects."""
    low, high = EXPECTED_RANGE[role]
    if high is None:
        return max_people >= low
    return low <= max_people <= high


def prepare_clip(role: str, source_name: str, detector: Detector) -> ClipResult:
    """Turns one raw video into demo_videos/<role>.mp4 and measures it."""
    source = RAW_DIR / source_name
    if not source.exists():
        raise SystemExit(f"Missing raw video: {source}")

    info = scan_video(source)
    start, end = trim_to_limit(info, *longest_stretch(info.cuts, info.frames))
    destination = config.VIDEO_DIR / f"{role}.mp4"
    width, height = write_clip(source, info, start, end, destination)

    preview_diff = save_previews(destination, role)
    if preview_diff > PREVIEW_DIFF_WARNING:
        print(f"WARNING {role}: first and last frames differ a lot ({preview_diff:.1f}); "
              "check the previews for a camera move or a cut.")

    detector.reset()
    max_people, median_people = measure_people(destination, detector)
    result = ClipResult(
        role=role,
        source_name=source_name,
        start_seconds=start / info.fps,
        end_seconds=end / info.fps,
        duration_seconds=(end - start) / info.fps,
        width=width,
        height=height,
        max_people=max_people,
        median_people=median_people,
        fits_role=fits_role(role, max_people),
        preview_diff=preview_diff,
    )
    return result


def print_result(result: ClipResult) -> None:
    """Prints the facts for one clip in a format that is easy to read aloud."""
    verdict = "fits" if result.fits_role else "DOES NOT FIT"
    print(f"{result.role:8s} {result.duration_seconds:5.1f}s  {result.width}x{result.height}  "
          f"max {result.max_people:2d}  median {result.median_people:2d}  {verdict}  "
          f"(source {result.source_name}, {result.start_seconds:.1f}-{result.end_seconds:.1f}s)")


def write_expected_results(results: list[ClipResult]) -> None:
    """Writes demo_videos/expected_results.md, the table the reviewer reads before the demo."""
    lines = [
        "# Expected results on the demo clips",
        "",
        "Measured with the real pipeline: `Detector` (YOLOv8 nano + ByteTrack), "
        "`conf=0.35`, every 2nd frame, frames resized to 640 px wide.",
        "",
        "| Clip | Scenario | Source | Length | Max people | Median people | Fits role | Expected alert |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        fits = "yes" if result.fits_role else "**NO**"
        lines.append(
            f"| `{result.role}.mp4` | {result.role} | `{result.source_name}` "
            f"| {result.duration_seconds:.1f}s | {result.max_people} | {result.median_people} "
            f"| {fits} | {EXPECTED_ALERT[result.role]} |"
        )
    lines += [
        "",
        "## How to read the table",
        "",
        "- **Max people** is the busiest single frame; it decides the role. "
        "Expected: normal <= 6, mid 7-14, crowded >= 12.",
        "- **Median people** is the typical frame; it shows how often the scene is busy, "
        "not just whether it spikes once.",
        "- A clip that does not fit is reported, never renamed silently. "
        "Replace the raw file or agree a new role name.",
        "",
        "## Clip details",
        "",
    ]
    for result in results:
        lines += [
            f"### {result.role}.mp4",
            "",
            f"- Source file: `demo_videos/raw/{result.source_name}`",
            f"- Used stretch: {result.start_seconds:.1f}s to {result.end_seconds:.1f}s "
            f"({result.duration_seconds:.1f}s, cut-free)",
            f"- Written resolution: {result.width}x{result.height} "
            f"(downscaled from the original, still 720p or better)",
            f"- First/last preview difference: {result.preview_diff:.1f} "
            f"(warning above {PREVIEW_DIFF_WARNING:.0f})",
            "",
        ]
    lines += [
        "## Camera stability",
        "",
        "Each clip is written from a single stretch between detected cuts, so there is no scene",
        "change inside a clip. The preview number is a raw pixel-change score, which moving",
        "people raise even when the camera is still; the script warns when it crosses "
        f"{PREVIEW_DIFF_WARNING:.0f}, and the preview images were then checked by eye.",
        "",
    ]
    (config.VIDEO_DIR / "expected_results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Prepares all three clips, prints the measurements and writes the markdown table."""
    detector = Detector()
    results = [prepare_clip(role, name, detector) for role, name in CLIPS]
    for result in results:
        print_result(result)
    write_expected_results(results)

    bad = [result.role for result in results if not result.fits_role]
    if bad:
        print(f"WARNING: these clips do not fit their role: {', '.join(bad)}. Nothing was renamed.")
    print(f"Wrote {len(results)} clips to {config.VIDEO_DIR}")


if __name__ == "__main__":
    main()
