"""Draws docs/architecture.png, the four-layer diagram for the README.

Why a generator script instead of a hand-drawn image: the diagram must be regenerable once the
project changes, and keeping the text in code means the labels cannot silently drift from reality.

Why these colours: they are the same CSS custom properties the dashboard uses (--bg, --panel,
--accent), so the diagram and the app look like one product.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---- palette, copied from static/style.css design tokens -------------------------------
BG = "#070b14"
PANEL = "#0d1424"
PANEL_EDGE = "#1e293b"
TEXT = "#e6edf7"
MUTED = "#8fa3bf"
ACCENT = "#38bdf8"
OK = "#22c55e"
WARN = "#f59e0b"
CRIT = "#ef4444"
PURPLE = "#a78bfa"

WIDTH, HEIGHT = 1560, 1240
MARGIN = 64

FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Loads a Windows TrueType font, falling back to the default if the file is missing.

    Why a fallback: the script must not crash on a machine without Segoe UI; the text would look
    worse but the diagram would still be produced.
    """
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = font("segoeuib.ttf", 46)
F_SUB = font("segoeui.ttf", 23)
F_LAYER = font("segoeuib.ttf", 27)
F_BADGE = font("segoeuib.ttf", 30)
F_CHIP = font("consola.ttf", 17)
F_DESC = font("segoeui.ttf", 19)
F_ARROW = font("segoeui.ttf", 17)
F_STRIP = font("segoeuib.ttf", 21)
F_STRIP_SUB = font("segoeui.ttf", 17)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    """Splits text into lines that each fit inside max_width, breaking on spaces.

    Why: layered text with no wrapping silently runs off the card edge, which is the most common
    way a generated diagram looks broken.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def chip(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, colour: str) -> int:
    """Draws one filename pill and returns the x where the next pill should start.

    Why pills: they make it obvious at a glance which files belong to which layer, which is the
    question a reviewer actually asks when they open the repo.
    """
    pad_x, pad_y = 12, 6
    w = draw.textlength(label, font=F_CHIP) + pad_x * 2
    h = 32
    draw.rounded_rectangle([x, y, x + w, y + h], radius=7, fill="#111c31", outline=colour,
                           width=1)
    draw.text((x + pad_x, y + pad_y), label, font=F_CHIP, fill=colour)
    return int(x + w + 12)


def layer_card(draw: ImageDraw.ImageDraw, y: int, number: str, title: str, files: list[str],
               desc: str, colour: str, height: int = 168) -> int:
    """Draws one numbered layer card and returns the y just below it.

    Why the coloured spine on the left: it gives each layer a visual identity, so a reader can
    follow the same colour down the arrows in the README text.
    """
    x0 = MARGIN
    x1 = WIDTH - MARGIN
    draw.rounded_rectangle([x0, y, x1, y + height], radius=16, fill=PANEL, outline=PANEL_EDGE,
                           width=2)
    # Coloured spine, drawn as a thick rounded bar so it reads as part of the card.
    draw.rounded_rectangle([x0, y, x0 + 10, y + height], radius=5, fill=colour)

    # Number badge.
    bx = x0 + 34
    draw.ellipse([bx, y + 22, bx + 46, y + 68], fill=colour)
    badge_text = number
    tw = draw.textlength(badge_text, font=F_BADGE)
    draw.text((bx + 23 - tw / 2, y + 28), badge_text, font=F_BADGE, fill="#08111f")

    # Layer name sits to the right of the badge.
    draw.text((bx + 66, y + 28), title, font=F_LAYER, fill=TEXT)

    # File pills, on the same line as the title where they fit.
    px = bx + 66 + draw.textlength(title, font=F_LAYER) + 26
    py = y + 30
    for label in files:
        needed = draw.textlength(label, font=F_CHIP) + 24 + 12
        if px + needed > x1 - 24:
            px = bx + 66
            py += 42
        px = chip(draw, int(px), py, label, colour)

    # Description, wrapped to the card width.
    text_x = bx + 66
    lines = wrap(draw, desc, F_DESC, x1 - text_x - 34)
    ty = y + 84
    for line in lines:
        draw.text((text_x, ty), line, font=F_DESC, fill=MUTED)
        ty += 27
    return y + height


def arrow(draw: ImageDraw.ImageDraw, y_top: int, y_bottom: int, label: str) -> None:
    """Draws a downward arrow with a label to its right.

    Why labelled arrows: the payload between two layers is the thing that proves the layers are
    actually decoupled, so the name of that payload belongs on the diagram.
    """
    cx = MARGIN + 46
    draw.line([cx, y_top + 8, cx, y_bottom - 14], fill=ACCENT, width=3)
    # Arrow head, as a filled triangle.
    draw.polygon([(cx - 9, y_bottom - 20), (cx + 9, y_bottom - 20), (cx, y_bottom - 4)],
                 fill=ACCENT)
    draw.text((cx + 26, (y_top + y_bottom) // 2 - 11), label, font=F_ARROW, fill=ACCENT)


def thread_strip(draw: ImageDraw.ImageDraw, y: int) -> None:
    """Draws the two-thread callout that explains why the architecture works.

    Why this is on the diagram at all: it is the single idea a panel will probe, and a diagram
    that shows four boxes without it misses the point of the design.
    """
    x0, x1 = MARGIN, WIDTH - MARGIN
    h = 150
    draw.rounded_rectangle([x0, y, x1, y + h], radius=16, fill="#0a1526", outline=ACCENT,
                           width=2)
    draw.text((x0 + 30, y + 20), "THE KEY IDEA", font=F_STRIP, fill=ACCENT)

    box_w = (x1 - x0 - 60 - 120) // 2
    by = y + 56
    bh = 72

    left = [x0 + 30, by, x0 + 30 + box_w, by + bh]
    draw.rounded_rectangle(left, radius=10, fill="#111c31", outline=OK, width=2)
    draw.text((left[0] + 16, by + 12), "ENGINE THREAD", font=F_STRIP, fill=OK)
    draw.text((left[0] + 16, by + 40), "read → detect → count → publish   ·   ~10–16 fps",
              font=F_STRIP_SUB, fill=MUTED)

    right_x = x1 - 30 - box_w
    right = [right_x, by, x1 - 30, by + bh]
    draw.rounded_rectangle(right, radius=10, fill="#111c31", outline=WARN, width=2)
    draw.text((right_x + 16, by + 12), "WEB THREAD", font=F_STRIP, fill=WARN)
    draw.text((right_x + 16, by + 40), "serves the last published result   ·   microseconds",
              font=F_STRIP_SUB, fill=MUTED)

    # The lock, drawn between the two boxes.
    mid_x = (left[2] + right_x) // 2
    mid_y = by + bh // 2
    draw.rounded_rectangle([mid_x - 42, mid_y - 26, mid_x + 42, mid_y + 26], radius=8,
                           fill="#0a1526", outline=ACCENT, width=2)
    lock = "LOCK"
    lw = draw.textlength(lock, font=F_CHIP)
    draw.text((mid_x - lw / 2, mid_y - 10), lock, font=F_CHIP, fill=ACCENT)
    draw.line([left[2], mid_y, mid_x - 44, mid_y], fill=PANEL_EDGE, width=2)
    draw.line([mid_x + 44, mid_y, right_x, mid_y], fill=PANEL_EDGE, width=2)


def main() -> None:
    """Builds the diagram and writes it to docs/architecture.png."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    draw.text((MARGIN, 40), "Crowd Density and Bottleneck Analytics",
              font=F_TITLE, fill=TEXT)
    draw.text((MARGIN, 98), "Four layers, one direction of data flow  ·  "
                           "CPU only  ·  YOLOv8 nano + ByteTrack + FastAPI + SQLite",
              font=F_SUB, fill=MUTED)

    y = 158
    y = layer_card(draw, y, "1", "INPUT",
                   ["demo_videos/*.mp4"],
                   "OpenCV VideoCapture reads one frame at a time from a local clip.",
                   ACCENT)
    arrow(draw, y, y + 62, "BGR frame, resized to 640 px wide")
    y += 62

    y = layer_card(draw, y, "2", "VISION AND RULES",
                   ["app/vision.py", "app/zones.py", "app/analytics.py"],
                   "YOLOv8 nano finds people, ByteTrack gives each a stable ID, and each foot "
                   "point is tested against the zone polygons. Dwell, speed, heatmap and the "
                   "alert debounce are computed here.",
                   OK)
    arrow(draw, y, y + 62, "snapshot dict + annotated frame")
    y += 62

    y = layer_card(draw, y, "3", "BACKEND AND STORAGE",
                   ["app/engine.py", "app/db.py", "app/main.py"],
                   "The engine thread runs the loop and publishes its result. SQLite keeps the "
                   "alert and headcount history. FastAPI serves REST, the WebSocket and MJPEG.",
                   WARN)
    arrow(draw, y, y + 62, "HTTP + WebSocket on 127.0.0.1:8000")
    y += 62

    y = layer_card(draw, y, "4", "WEB DASHBOARD",
                   ["static/index.html", "static/app.js", "static/style.css"],
                   "Live video with bounding boxes, zone polygons and the density heatmap. Four "
                   "KPI tiles, ring gauges per zone, a headcount chart and the congestion banner.",
                   PURPLE)

    thread_strip(draw, y + 34)

    out = Path("docs")
    out.mkdir(exist_ok=True)
    target = out / "architecture.png"
    img.save(target, "PNG", optimize=True)
    print(f"wrote {target}  ({target.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
