"""Crops docs/dashboard.png into a print-friendly figure for the handbook.

Why crop: the README screenshot is a whole-page capture, 1440 px wide. Placed in an A4 document at
a readable width it is fine, but it carries the footer and the empty space beneath it, which wastes
vertical room on the page. The crop keeps the top bar down to the bottom of the camera and chart
panels, which is the part that actually demonstrates the app.

The source is produced by scripts/make_screenshot.py; run that first if the picture looks stale.
"""

from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "docs" / "dashboard.png"
OUT = BASE / "docs" / "dashboard_figure.png"

# Keep the top bar, the readings strip, the camera, the occupancy meters, the site plan, the start
# of the event log and the whole chart. The crop stops just under the chart so the figure ends on a
# panel edge rather than halfway through the footer.
CROP_HEIGHT = 1020

img = Image.open(SRC)
width, height = img.size
if height <= CROP_HEIGHT:
    # A shorter capture is already cropped; copy it through rather than failing the build.
    CROP_HEIGHT = height

cropped = img.crop((0, 0, width, CROP_HEIGHT))
cropped.save(OUT, "PNG", optimize=True)
print(f"wrote {OUT}  {cropped.size[0]}x{cropped.size[1]}  "
      f"({OUT.stat().st_size / 1024:.0f} KB)")
