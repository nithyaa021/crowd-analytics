"""All tunable settings for the app live here.

The rest of the code imports these names, so we never hide a "magic number" inside
a function and we can change behaviour by editing this one file.
"""

from pathlib import Path

# ---------- AI model and detection ----------

# Weights file for YOLOv8 nano; ultralytics downloads it into the project on first use.
MODEL_PATH = "yolov8n.pt"

# Minimum YOLO confidence (0 to 1) for a box to count as a person; 0.35 filters weak guesses.
CONF = 0.35

# Image size the model sees, in pixels; 640 is the standard YOLOv8 size and works on CPU.
IMGSZ = 640

# YOLO class number for "person"; class 0 of the 80 COCO classes, the only one we count.
PERSON_CLASS_ID = 0

# Width every frame is resized to, in pixels; smaller frames are faster to process and draw.
FRAME_WIDTH = 640

# Process every Nth frame only (2 = every second frame); tracking still follows all people.
STRIDE = 2

# ---------- Capacity alert timing ----------

# Seconds a zone must stay above capacity before we raise an alert (ignores 1-frame spikes).
ON_DELAY = 3.0

# Seconds a zone must stay at or below capacity before we clear the alert (avoids flicker).
OFF_DELAY = 5.0

# ---------- Analytics and tracking ----------

# How close two people must be to count as a bottleneck, as a fraction of their box width.
NEAR_RATIO = 0.8

# Multiplier applied to the heatmap every frame (0.995 ≈ a hot spot fades to 61% after 100 frames).
HEAT_DECAY = 0.995

# Blur width for the drawn heatmap, as a fraction of the frame width; 0.05 at 640 px = a 33 px
# kernel, which turns single-pixel hits into a visible soft blob.
HEAT_BLUR_FRACTION = 0.05

# A heatmap pixel is drawn only if it holds at least this fraction of the hottest pixel, so the
# empty parts of the floor stay clean instead of being tinted blue.
HEAT_MASK_RATIO = 0.08

# How strongly the heatmap colour replaces the video where the mask is true (0.5 = half and half).
HEAT_OVERLAY_ALPHA = 0.5

# Seconds a lost track ID is remembered before we treat the person as gone.
TRACK_GRACE = 2.0

# ---------- Video and web output ----------

# JPEG quality (1 to 100) used when the server streams frames to the browser.
JPEG_QUALITY = 80

# Maximum frames per second the MJPEG stream sends, so a slow browser is not flooded.
MJPEG_MAX_FPS = 15

# Seconds between live status messages pushed to the dashboard over WebSocket.
WS_INTERVAL = 0.5

# ---------- Folders and files (absolute, so the app works from any working directory) ----------

# Project root, i.e. the folder that contains app/, static/, tests/ ...
BASE_DIR = Path(__file__).resolve().parent.parent

# Where the demo videos live.
VIDEO_DIR = BASE_DIR / "demo_videos"

# Where alert snapshots (evidence photos) are saved.
EVIDENCE_DIR = BASE_DIR / "evidence"

# Where processed videos and exported results are written.
OUTPUT_DIR = BASE_DIR / "outputs"

# The JSON file that stores the operator's zones and their capacities.
ZONES_FILE = BASE_DIR / "zones.json"

# SQLite database file that keeps the alert history.
DB_PATH = BASE_DIR / "results" / "crowd.db"
