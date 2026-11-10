"""Crops docs/dashboard.png into a print-friendly figure for the handbook.

Why crop: the GitHub screenshot is a tall 777x2385 capture of the whole page. Scaled to a
readable width it becomes 13 inches tall and overflows an A4 page. The top section - congestion
banner, KPI row, live video and the start of the chart - is what actually demonstrates the app,
so that is what the printed figure shows.
"""

from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "docs" / "dashboard.png"
OUT = BASE / "docs" / "dashboard_figure.png"

# Keep the banner, the four KPI tiles and the whole live video card. y=1180 is where the video
# card's bottom edge sits, so the crop ends on a clean boundary instead of mid-panel.
CROP_HEIGHT = 1180

img = Image.open(SRC)
width, height = img.size
if height <= CROP_HEIGHT:
    raise SystemExit(f"source is only {height}px tall; nothing to crop")

cropped = img.crop((0, 0, width, CROP_HEIGHT))
cropped.save(OUT, "PNG", optimize=True)
print(f"wrote {OUT}  {cropped.size[0]}x{cropped.size[1]}  "
      f"({OUT.stat().st_size / 1024:.0f} KB)")
