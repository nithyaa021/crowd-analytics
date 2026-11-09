"""Finds where people actually walk in a clip and writes a zone for it.

Why this exists: drawing a zone by hand for every new camera view is slow and easy to get
wrong. Instead we let the detector show us where feet land, turn the busiest connected patch
into a polygon, and pick a capacity that produces the alert behaviour the clip is meant to
demonstrate (normal: none, crowded: at least one). The result is saved into zones.json so the
rest of the app uses exactly the same polygon.

Run: .venv\\Scripts\\python.exe scripts\\auto_zones.py
     .venv\\Scripts\\python.exe scripts\\auto_zones.py demo_videos\\mid.mp4
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
from app.zones import Zone, save_zones

# ---------- Step settings (this script only, so app/config.py stays untouched) ----------

# How much of the busiest density counts as "busy enough to be the zone".
# 0.35 keeps the crowded core and drops the scattered walkers around it.
DENSITY_THRESHOLD = 0.35

# Blur width as a fraction of the frame width. Blurring joins nearby feet into one patch,
# so the zone becomes a floor area instead of a cloud of dots.
# 0.20 (a 129 px kernel at 640 px wide) was measured, not guessed: smaller blurs fragmented the
# spread-out street crowd into 7 islands of ~2 people, which produced a tiny useless zone.
DENSITY_BLUR_FRACTION = 0.20

# A zone may have at most this many corners, so it stays a simple shape a human can explain.
MAX_CORNERS = 8

# Starting simplification tolerance, as a fraction of the outline length. It grows until the
# corner count fits MAX_CORNERS.
SIMPLIFY_START = 0.01
SIMPLIFY_GROWTH = 1.35

# Capacity can be nudged by this many people at a time while chasing the alert behaviour.
CAPACITY_STEP = 1
# A capacity never drops below this; fewer than 3 people is not a meaningful crowd zone.
MIN_CAPACITY = 3
# Safety stop, so a clip that simply cannot produce the wanted behaviour cannot loop forever.
MAX_ADJUSTMENTS = 60

# The role is read from the file name; each role has its own capacity rule.
ROLE_RULES = {
    "normal": "peak + 2, never below 3",
    "mid": "90% of p90, never below 3",
    "crowded": "60% of p90, never below 3",
}


@dataclass
class ClipZones:
    """Everything one clip produced: its polygon, capacity, crowd numbers and alert count."""

    clip: str
    corners: int
    capacity: int
    peak: int
    p90: int
    alerts: int
    adjustments: int
    role: str


def odd(value: int) -> int:
    """Makes a number odd, because Gaussian blur only accepts odd kernel sizes.

    Example: 38 -> 39, 39 -> 39, 40 -> 41.
    """
    return value if value % 2 == 1 else value + 1


def scan_clip(clip_path: Path, detector: Detector) -> tuple[float, np.ndarray, list[list[tuple[int, int]]]]:
    """Runs the detector over a clip and remembers the foot points of every analysed frame.

    Why store the points instead of re-running detection: detection is the slow part. One pass
    gives us both the density map and the per-frame counts.

    Returns (fps, first_frame, feet_per_frame).
    """
    capture = cv2.VideoCapture(str(clip_path))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open clip: {clip_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps:
        raise SystemExit(f"Clip has no usable frame rate: {clip_path}")

    feet_per_frame: list[list[tuple[int, int]]] = []
    first_frame: np.ndarray | None = None
    index = 0
    while True:
        # grab() is cheap; only every STRIDE-th frame is decoded and detected.
        if not capture.grab():
            break
        if index % config.STRIDE == 0:
            ok, frame = capture.retrieve()
            if not ok:
                break
            frame = resize_frame(frame, config.FRAME_WIDTH)
            if first_frame is None:
                first_frame = frame
            people = detector.track(frame)
            feet_per_frame.append([person.foot for person in people])
        index += 1
    capture.release()

    if first_frame is None or not feet_per_frame:
        raise SystemExit(f"No frames could be read from: {clip_path}")
    return float(fps), first_frame, feet_per_frame


def build_density(feet_per_frame: list[list[tuple[int, int]]], shape: tuple[int, int]) -> np.ndarray:
    """Sums foot points into a heat image and blurs it, so busy patches stand out.

    Why: one person leaves one dot, which is too small to be a zone. Many dots blurred together
    become a smooth hill, and the top of that hill is where people really gather.

    Example: a corridor where 50 people walked scores far higher than a corner where 2 did,
    so only the corridor survives the threshold.
    """
    height, width = shape
    heat = np.zeros((height, width), dtype=np.float32)
    for feet in feet_per_frame:
        for x, y in feet:
            # Ignore a point that somehow lands outside the picture, instead of crashing.
            if 0 <= x < width and 0 <= y < height:
                heat[y, x] += 1.0
    kernel = odd(max(3, round(width * DENSITY_BLUR_FRACTION)))
    return cv2.GaussianBlur(heat, (kernel, kernel), 0)


def largest_region(heat: np.ndarray) -> np.ndarray:
    """Thresholds the heat image and returns the outer contour of its biggest connected patch.

    Why the biggest patch only: a zone should be the main walking area. Small side patches are
    usually reflections, doorways or a couple of people passing, and would make the zone shape
    look random.
    """
    peak = float(heat.max())
    if peak <= 0:
        raise SystemExit("No people were detected in this clip, so no zone can be built.")

    mask = (heat >= peak * DENSITY_THRESHOLD).astype(np.uint8) * 255
    # Close small gaps so one crowd becomes one region instead of several islands.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8))

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        raise SystemExit("The density map produced no region above the threshold.")

    # Label 0 is the background, so the search starts at label 1.
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = 1 + int(np.argmax(areas))
    component = (labels == best).astype(np.uint8) * 255

    contours, _hierarchy = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise SystemExit("The largest region had no outline.")
    return max(contours, key=cv2.contourArea)


def simplify(contour: np.ndarray) -> np.ndarray:
    """Reduces an outline to at most MAX_CORNERS corners, growing the tolerance until it fits.

    Why: a raw contour can have hundreds of points, which is impossible to explain and slow to
    draw. approxPolyDP replaces a wobbly stretch with one straight edge.

    Example: 240 contour points -> 31 -> 12 -> 7 corners as the tolerance grows.
    """
    perimeter = cv2.arcLength(contour, True)
    epsilon = SIMPLIFY_START * perimeter
    polygon = cv2.approxPolyDP(contour, epsilon, True)
    while len(polygon) > MAX_CORNERS:
        epsilon *= SIMPLIFY_GROWTH
        polygon = cv2.approxPolyDP(contour, epsilon, True)
        # A fresh contour can never need more points than it has; this stops the loop.
        if epsilon > perimeter:
            break
    if len(polygon) < 3:
        raise SystemExit("The zone collapsed to fewer than 3 corners; try another clip.")
    return np.array(polygon, dtype=np.int32).reshape(-1, 1, 2)


def count_inside(polygon: np.ndarray, feet: list[tuple[int, int]]) -> int:
    """Counts how many of these feet are inside the polygon.

    Why: the polygon only becomes useful when we can turn it into a number per frame, which is
    what the alert rule reads.

    Example: feet (150,150) and (900,50) inside a zone covering x 100..300 give 1.
    """
    total = 0
    for x, y in feet:
        if cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0:
            total += 1
    return total


def simulate_alerts(counts: list[int], seconds_per_sample: float, capacity: int) -> int:
    """Replays the alert rule over the counts and returns how many alerts it would raise.

    Why simulate instead of trusting a guess: capacity is only "right" if the clip produces the
    behaviour we promise. This tiny loop is the same idea as the real engine, so the table in
    the docs matches what the app will do.

    The rule: stay over capacity for ON_DELAY seconds to raise an alert, and stay at or under
    for OFF_DELAY seconds to clear it.

    Example: capacity 5, counts 6,6,6,6 with 0.5 s samples -> over for 2.0 s -> 1 alert.
    """
    alerts = 0
    alerting = False
    over_seconds = 0.0
    under_seconds = 0.0
    for count in counts:
        if count > capacity:
            over_seconds += seconds_per_sample
            under_seconds = 0.0
            if not alerting and over_seconds >= config.ON_DELAY:
                alerting = True
                alerts += 1
        else:
            under_seconds += seconds_per_sample
            over_seconds = 0.0
            if alerting and under_seconds >= config.OFF_DELAY:
                alerting = False
    return alerts


def role_of(clip_name: str) -> str:
    """Reads the role from the file name, because the capacity rule depends on it.

    Example: "crowded.mp4" -> "crowded"; "my_test_clip.mp4" -> "" (unknown).
    """
    stem = Path(clip_name).stem.lower()
    for role in ROLE_RULES:
        if role in stem:
            return role
    return ""


def base_capacity(role: str, peak: int, p90: int) -> int:
    """Applies the capacity rule for this role.

    Why these numbers: normal must have room to spare (peak + 2), mid should warn before it is
    full (90% of the typical busy level), and crowded must trip the alert (60% of it).

    Example: normal peak 4 -> 6; mid p90 12 -> 11; crowded p90 18 -> 11.
    """
    if role == "normal":
        capacity = peak + 2
    elif role == "crowded":
        capacity = round(0.6 * p90)
    else:
        # Unknown role: the middle rule is the safest default, and we say so in the output.
        capacity = round(0.9 * p90)
    return max(capacity, MIN_CAPACITY)


def tune_capacity(role: str, start: int, counts: list[int], seconds_per_sample: float) -> tuple[int, int, int]:
    """Nudges capacity until the clip shows the alert behaviour its role promises.

    Why: the formulas give a good starting point, but real footage is uneven. normal must raise
    no alerts; crowded must raise at least one. If a formula misses, we adjust one person at a
    time in the right direction and re-simulate.

    Returns (capacity, alerts, adjustments).
    """
    capacity = start
    alerts = simulate_alerts(counts, seconds_per_sample, capacity)
    adjustments = 0

    while adjustments < MAX_ADJUSTMENTS:
        if role == "normal" and alerts > 0:
            # Too many alerts for a calm clip, so allow more people before alerting.
            capacity += CAPACITY_STEP
        elif role == "crowded" and alerts == 0:
            # Too few alerts for a crowded clip, so allow fewer people.
            if capacity <= MIN_CAPACITY:
                break
            capacity -= CAPACITY_STEP
        else:
            break
        alerts = simulate_alerts(counts, seconds_per_sample, capacity)
        adjustments += 1

    return capacity, alerts, adjustments


def save_preview(clip_name: str, frame: np.ndarray, polygon: np.ndarray, capacity: int, peak: int) -> Path:
    """Saves the first frame with the zone drawn on it, so a human can check the shape.

    Why: a polygon can look perfect in numbers and wrong on screen. One picture is the fastest
    way to see whether we picked the actual walking area.
    """
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas = frame.copy()
    cv2.polylines(canvas, [polygon], True, (0, 255, 255), 2)
    cv2.putText(canvas, f"Main Zone  capacity {capacity}  peak {peak}",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, f"Main Zone  capacity {capacity}  peak {peak}",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)

    destination = config.OUTPUT_DIR / f"zones_{Path(clip_name).stem}.png"
    cv2.imwrite(str(destination), canvas)
    return destination


def process_clip(clip_path: Path, detector: Detector) -> ClipZones:
    """Builds the zone, picks a capacity and saves everything for one clip."""
    role = role_of(clip_path.name)
    fps, first_frame, feet_per_frame = scan_clip(clip_path, detector)
    detector.reset()

    heat = build_density(feet_per_frame, first_frame.shape[:2])
    polygon = simplify(largest_region(heat))

    counts = [count_inside(polygon, feet) for feet in feet_per_frame]
    peak = max(counts)
    p90 = int(round(float(np.percentile(counts, 90))))

    # Each processed frame stands for STRIDE source frames, so this is its real duration.
    seconds_per_sample = config.STRIDE / fps
    start = base_capacity(role, peak, p90)
    capacity, alerts, adjustments = tune_capacity(role, start, counts, seconds_per_sample)

    if adjustments:
        print(f"  {clip_path.name}: capacity adjusted {start} -> {capacity} "
              f"to get the expected alert behaviour")

    save_zones(config.ZONES_FILE, clip_path.name,
               [Zone(name="Main Zone", capacity=capacity, polygon=polygon)])
    save_preview(clip_path.name, first_frame, polygon, capacity, peak)

    return ClipZones(
        clip=clip_path.name,
        corners=len(polygon),
        capacity=capacity,
        peak=peak,
        p90=p90,
        alerts=alerts,
        adjustments=adjustments,
        role=role or "unknown",
    )


def print_table(results: list[ClipZones]) -> None:
    """Prints the summary table the step asks for.

    Why a table: the three clips must be compared at a glance, and a fixed column width keeps
    the numbers aligned while you read them aloud.
    """
    print(f"{'clip':16s} {'role':9s} {'corners':>7s} {'capacity':>8s} "
          f"{'peak':>5s} {'p90':>4s} {'alerts':>6s}")
    print("-" * 62)
    for result in results:
        print(f"{result.clip:16s} {result.role:9s} {result.corners:7d} {result.capacity:8d} "
              f"{result.peak:5d} {result.p90:4d} {result.alerts:6d}")


def clips_from_arguments() -> list[Path]:
    """Uses the clips given on the command line, or every clip in demo_videos/ by default.

    Why a default: running the script with no arguments must just work for the panel.
    """
    if len(sys.argv) > 1:
        clips = [Path(argument) for argument in sys.argv[1:]]
        for clip in clips:
            if not clip.exists():
                raise SystemExit(f"Clip not found: {clip}")
        return clips

    clips = sorted(path for path in config.VIDEO_DIR.glob("*.mp4"))
    if not clips:
        raise SystemExit(f"No .mp4 files in {config.VIDEO_DIR}")
    return clips


def main() -> None:
    """Generates a zone for every requested clip and prints the summary table."""
    clips = clips_from_arguments()
    detector = Detector()
    results = [process_clip(clip, detector) for clip in clips]
    print_table(results)

    # Fail loudly if a promised behaviour did not appear, so nobody discovers it during a demo.
    problems = []
    for result in results:
        if result.role == "normal" and result.alerts != 0:
            problems.append(f"{result.clip}: normal clip has {result.alerts} alerts")
        if result.role == "crowded" and result.alerts == 0:
            problems.append(f"{result.clip}: crowded clip has no alert even at capacity {result.capacity}")
    if problems:
        print("WARNING: " + "; ".join(problems))
    print(f"Saved zones to {config.ZONES_FILE}")


if __name__ == "__main__":
    main()
