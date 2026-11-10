"""Builds the interview handbook (docs/Crowd_Analytics_Handbook.docx).

Why a generator instead of writing the .docx by hand: the Word file must stay in step with the
code, and a script that reads the real repository can be re-run whenever something changes.

Why python-docx: it writes a real .docx (headings, tables, images) with no Word automation, so it
works even if Word is closed.
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "Crowd_Analytics_Handbook.docx"

# ---- palette, matching the dashboard so the document feels part of the product --------------
INK = RGBColor(0x1A, 0x1A, 0x1A)
ACCENT = RGBColor(0x0E, 0x74, 0x90)
MUTED = RGBColor(0x55, 0x5F, 0x6D)
CRIT = RGBColor(0xB9, 0x1C, 0x1C)

doc = Document()

# Tracks whether the next heading should start a fresh page. Set by pagebreak().
_pending_break = False

# Counter for numbered(). A one-item list, so numbered() can update it from inside a function.
_num = [0]


def _restart_numbers() -> None:
    """Starts the next numbered list again at 1.

    Called by every heading and paragraph, because a list is always a distinct block of steps and
    should not inherit the count from whatever list came before it.
    """
    _num[0] = 0

# Base font: Calibri is on every Windows machine, so the file looks the same on any laptop.
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(10.5)
style.font.color.rgb = INK
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.12


def setup_page() -> None:
    """Sets A4 with sensible margins, because the panel may print this."""
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)


def heading(text: str, level: int = 1) -> None:
    """Adds a styled heading and keeps spacing tight enough that pages are not half empty.

    Why the pending-break flag: a page break inserted as its own empty paragraph leaves a blank
    page behind it. Asking the NEXT heading to start a new page avoids that entirely.
    """
    global _pending_break
    _restart_numbers()
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = ACCENT if level <= 2 else INK
        run.font.name = "Calibri"
    if level == 1:
        h.paragraph_format.space_before = Pt(16)
        h.paragraph_format.space_after = Pt(6)
    if _pending_break:
        h.paragraph_format.page_break_before = True
        _pending_break = False


def para(text: str, bold: bool = False, size: float = 10.5, colour=None) -> None:
    """Adds a normal paragraph with optional emphasis."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if colour is not None:
        run.font.color.rgb = colour
    return p


def bullet(text: str, bold_prefix: str = "") -> None:
    """Adds a bullet; an optional bold prefix keeps the point readable at a glance."""
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    if bold_prefix:
        run = p.add_run(bold_prefix)
        run.bold = True
    p.add_run(text)


def numbered(text: str) -> None:
    """Adds a numbered step, used for the demo script where order matters.

    Why the number is written by hand instead of using the built-in List Number style: Word
    numbers every List Number paragraph in the document as one continuous sequence, so a second
    list started at "8." instead of "1.". A local counter that any other block resets keeps each
    list correct no matter what comes before it.
    """
    global _num
    _num[0] += 1
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    # Hanging indent so the wrapped lines line up under the text, not under the number.
    p.paragraph_format.left_indent = Inches(0.32)
    p.paragraph_format.first_line_indent = Inches(-0.22)
    run = p.add_run(f"{_num[0]}.  ")
    run.bold = True
    p.add_run(text)


def code(text: str) -> None:
    """Adds a monospace block for commands, on a light grey background."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.2)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F1F5F9")
    p._p.get_or_add_pPr().append(shd)
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9.5)


def table(headers: list[str], rows: list[list[str]], width: float | None = None) -> None:
    """Adds a bordered table with a coloured header row.

    Why every table gets a header shading: a long table of file names is unreadable on a printed
    page without a visual anchor at the top.

    Why the header row repeats: a table that spills over a page boundary otherwise continues with
    anonymous columns, and the config table on page 4 does exactly that.
    """
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    # Mark row 0 as a true header row so Word repeats it at the top of every following page.
    tr_pr = t.rows[0]._tr.get_or_add_trPr()
    header_flag = OxmlElement("w:tblHeader")
    header_flag.set(qn("w:val"), "true")
    tr_pr.append(header_flag)
    # A header row must never be split down the middle; a cell cut in half reads as a defect.
    tr_pr.append(OxmlElement("w:cantSplit"))
    for i, name in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        # Bind the header to the first data row at the PARAGRAPH level (a row-level
        # w:keepWithNext is not a valid table property, so Word ignores it). Without this the
        # coloured header can be left alone at the foot of a page with its rows overleaf.
        p.paragraph_format.keep_with_next = True
        run = p.add_run(name)
        run.bold = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "0E7490")
        hdr[i]._tc.get_or_add_tcPr().append(shd)
    for row in rows:
        cells = t.add_row().cells
        # Keep a row on one page; a cell split down the middle reads as a printing error.
        row_pr = t.rows[-1]._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        row_pr.append(cant_split)
        for i, value in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(value))
            run.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def callout(title: str, text: str, colour=ACCENT) -> None:
    """Adds a single-cell shaded box for a tip or a warning the reader must not miss."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F0F7FA")
    cell._tc.get_or_add_tcPr().append(shd)
    p = cell.paragraphs[0]
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = colour
    p2 = cell.add_paragraph()
    run2 = p2.add_run(text)
    run2.font.size = Pt(9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def pagebreak() -> None:
    """Marks that the next heading should start a new page.

    Why a flag and not an inserted break: adding a break as its own paragraph creates a blank page
    whenever the previous content already ended near a page boundary. Setting page_break_before on
    the following heading is exact.
    """
    global _pending_break
    _pending_break = True


# =============================================================================================
# COVER
# =============================================================================================

setup_page()

# One blank line of breathing room, not three: the cover must hold the title AND the screenshot
# on a single page, and every extra empty paragraph pushed the image onto page 2.
doc.add_paragraph()

title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run("Crowd Density and Bottleneck Analytics")
run.bold = True
run.font.size = Pt(28)
run.font.color.rgb = ACCENT

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = sub.add_run("Project Handbook and Interview Guide")
run.font.size = Pt(15)
run.font.color.rgb = MUTED

doc.add_paragraph()

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = meta.add_run("Cogno Valley Internship  -  Track A\n"
                   "YOLOv8 nano + ByteTrack  -  FastAPI  -  SQLite  -  CPU only")
run.font.size = Pt(11)
run.font.color.rgb = MUTED

img_path = BASE / "docs" / "dashboard_figure.png"
if img_path.exists():
    # 4.0 in wide gives about 6.1 in tall for this 777x1180 crop, which leaves room for the
    # title block above and the caption below inside one A4 page.
    doc.add_picture(str(img_path), width=Inches(4.0))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.paragraphs[-1].paragraph_format.space_before = Pt(10)
    doc.paragraphs[-1].paragraph_format.space_after = Pt(4)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run("The dashboard during a congestion alert")
    run.font.size = Pt(9)
    run.italic = True
    run.font.color.rgb = MUTED

pagebreak()

# =============================================================================================
# CONTENTS
# =============================================================================================

heading("What is in this document", 1)

para("This is the single document to read before the interview. It covers what the project is, "
     "what every file does, how to run it, how to demo it, and how to answer the questions a "
     "technical panel is likely to ask.")

table(
    ["Part", "What it gives you", "Read it when"],
    [
        ["1. The project in one page", "The pitch and the three questions it answers", "First, always"],
        ["2. Folder and file guide", "Every file, its job, and why it exists", "Before any code question"],
        ["3. How it works end to end", "The frame-by-frame data flow", "Before the demo"],
        ["4. The numbers", "Worked arithmetic you can say out loud", "An hour before"],
        ["5. How to run it", "Exact commands, plus what each does", "The night before"],
        ["6. How to demo it", "A timed 3-minute script", "Rehearse twice"],
        ["7. Interview answers", "Q&A with short, defensible answers", "Last"],
        ["8. Honest limitations", "What to admit, and how to say it", "If pushed"],
    ],
)

callout("Before anything else",
        "Open a terminal in the project folder and run .\\start.bat. The dashboard is up in about "
        "15 seconds. Everything in this document is easier to understand with the app running "
        "beside it.")

pagebreak()

# =============================================================================================
# PART 1 - THE PITCH
# =============================================================================================

heading("Part 1 - The project in one page", 1)

heading("The problem", 2)
para("A station concourse, a shop floor or a campus corridor gets crowded. By the time a human "
     "notices on a camera monitor, the queue has already formed and people are already stuck. "
     "Someone standing in front of 12 screens cannot watch all of them, and cannot do arithmetic "
     "about how long a crowd has been building.")

heading("What this project does", 2)
para("It watches a video feed and answers three questions continuously, without a human watching:")

bullet("how many people are standing in each monitored area, right now.", "1. Occupancy - ")
bullet("how long each person has stayed, and whether they are walking or stuck.", "2. Dwell and flow - ")
bullet("is any area holding more people than it safely can, and for how long.", "3. Capacity - ")

para("When an area has been over capacity for 3 continuous seconds, the app raises an alert, saves "
     "a photo of the exact frame that caused it, and shows a red banner on the dashboard.")

heading("The 30-second version to say out loud", 2)

callout("Say this",
        "\"This is a crowd density and bottleneck analytics dashboard. A background thread runs "
        "YOLOv8 to find people and ByteTrack to give each one a stable ID, then counts them inside "
        "hand-drawn zones. It tracks how long people stay and how fast they move, builds a density "
        "heatmap, and raises an alert only when a zone has been over capacity for three continuous "
        "seconds - so a single bad detection cannot trigger it. A FastAPI server pushes all of "
        "that to a live dashboard with the annotated video, occupancy meters and a headcount chart. "
         "It runs on a CPU, offline, with open-source parts only.\"")

heading("The stack, and why each piece", 2)

table(
    ["Piece", "What it does", "Why this one"],
    [
        ["YOLOv8 nano", "Finds people in a frame", "Smallest YOLO variant; the only size that holds real time on a 4-core CPU"],
        ["ByteTrack", "Gives each person a stable ID across frames", "Ships inside ultralytics, so no extra dependency"],
        ["OpenCV", "Reads video, draws boxes and zones, encodes JPEG", "The standard, and ultralytics already needs it"],
        ["FastAPI", "Serves the dashboard, API, WebSocket and video", "Async, tiny, and generates its own docs"],
        ["SQLite", "Stores alerts and headcount history", "Standard library, one file, zero setup"],
        ["Plain HTML + Tailwind + Chart.js", "The dashboard", "No build step, so nothing can break before a demo"],
    ],
)

pagebreak()

# =============================================================================================
# PART 2 - FOLDER AND FILES
# =============================================================================================

heading("Part 2 - The folder, file by file", 1)

para("The whole application is 7 Python files, 3 web files, 1 config file, 1 test file and 1 zones "
     "file. That is deliberate: a project you cannot explain is not finished. Learn this part and "
     "you can answer any code question.")

heading("The folder tree", 2)

code("""crowd-analytics/
├── app/                     the Python application
│   ├── config.py            every tunable number, in one place
│   ├── vision.py            YOLO + ByteTrack: finds and tracks people
│   ├── zones.py             zone polygons, capacity, the OK/NEAR/OVER rule
│   ├── analytics.py         dwell time, speed, heatmap, alert debounce
│   ├── db.py                SQLite: alerts table + headcount table
│   ├── engine.py            the background video loop + SharedState
│   └── main.py              FastAPI routes (the whole web layer)
├── static/                  the dashboard (no build step)
│   ├── index.html           page structure
│   ├── app.js               fetches data, draws meters, plan, chart, alerts
│   ├── style.css            the operations console theme
│   └── vendor/              Tailwind + Chart.js, so no CDN is needed
├── tests/
│   └── test_pipeline.py     20 tests, in data-flow order
├── demo_videos/             three clips + expected_results.md + SOURCES.csv
├── docs/                    architecture.png, dashboard.png, this handbook
├── scripts/                 make_architecture.py (regenerates the diagram)
├── results/                 crowd.db is created here on first run
├── zones.json               zone polygons and capacities, per clip
├── CODE_GUIDE.md            the long-form code walkthrough
├── README.md                the repo front page
├── requirements.txt         pinned dependencies
└── start.bat                double-click launcher""")

heading("The Python files, one by one", 2)

heading("app/config.py - 67 lines - every number lives here", 3)
para("Why it exists: the brief forbids magic numbers. Every threshold is a named constant, so "
     "behaviour can be changed by editing one file, and you can always point at a name instead of "
     "a stray 0.35 buried in a function.")

table(
    ["Constant", "Value", "What it controls"],
    [
        ["MODEL_PATH", "yolov8n.pt", "Which YOLO weights to load"],
        ["CONF", "0.35", "Minimum confidence for a box to count as a person"],
        ["IMGSZ", "640", "The square size the model sees"],
        ["PERSON_CLASS_ID", "0", "COCO class 0 is person; the other 79 classes are ignored"],
        ["FRAME_WIDTH", "640", "Every frame is resized to this width"],
        ["STRIDE", "2", "Analyse every 2nd frame"],
        ["ON_DELAY", "3.0 s", "Seconds over capacity before an alert fires"],
        ["OFF_DELAY", "5.0 s", "Seconds back to normal before it clears"],
        ["NEAR_RATIO", "0.8", "Fraction of capacity that shows amber NEAR"],
        ["HEAT_DECAY", "0.995", "How fast old heatmap heat fades"],
        ["TRACK_GRACE", "2.0 s", "How long a lost track is remembered"],
        ["JPEG_QUALITY", "80", "Stream image quality"],
        ["MJPEG_MAX_FPS", "15", "Cap on the video stream rate"],
        ["WS_INTERVAL", "0.5 s", "How often the WebSocket pushes numbers"],
        ["HEADCOUNT_INTERVAL", "2.0 s", "How often a headcount row is saved"],
        ["DEFAULT_SOURCE", "crowded.mp4", "Which clip plays on startup"],
    ],
)

heading("app/vision.py - 92 lines - the eyes", 3)
para("Why it exists: it is the only file that knows what YOLO is. Everything else asks for "
     "\"people\" and gets a clean list. Swap the detector and only this file changes.")

bullet("One detected person in one frame: track_id, box, conf, foot.", "Person (dataclass) - ")
bullet("Returns the bottom-centre of a box. A box centre sits at chest height, but zones are "
       "drawn on the floor. Example: box (100,50,140,200) gives (120,200).",
       "foot_point(box) - ")
bullet("Resizes to a fixed width keeping aspect ratio. 1280x720 at width 640 becomes 640x360.",
       "resize_frame(frame, width) - ")
bullet("The core call: YOLO track with persist=True, tracker=bytetrack.yaml, classes=[0], "
       "conf=0.35. Returns a list of Person.", "Detector.track(frame) - ")
bullet("Restarts tracking IDs at 1 when switching clips, so dwell times are not inherited.",
       "Detector.reset() - ")

heading("app/zones.py - 200 lines - geometry and the status rule", 3)
para("Why it exists: the dashboard, the counting and the alert all ask the same question - which "
     "zone is this person in, and is it full? - and they must get the same answer.")

bullet("name, capacity, polygon, stored as the (N,1,2) int32 array OpenCV wants.", "Zone (dataclass) - ")
bullet("Loads the zones for one clip. Per clip, because every camera angle differs.",
       "load_zones(path, source_name) - ")
bullet("Returns the first zone containing a point, or None. First match wins because polygons "
       "can overlap.", "zone_of(zones, point) - ")
bullet("Groups people by the zone their feet are in. Starts every zone empty so a zone with "
       "nobody in it still shows 0/5.", "count_by_zone(zones, people) - ")
bullet("The most important small function. Over capacity means strictly more: exactly full is "
       "still NEAR. Example with capacity 10: 7 OK, 8 NEAR, 10 NEAR, 11 OVER.",
       "status_for(count, capacity) - ")
bullet("Draws each polygon on a copy, coloured by status, with a label like \"Main Zone 6/5\".",
       "draw_zones(frame, zones, counts) - ")

heading("app/analytics.py - 303 lines - memory over time", 3)
para("Why it exists: counting people in one frame is easy. The interesting answers need to "
     "remember the past. Every timestamp in this file is VIDEO time, never the wall clock, "
     "because the demo replays a recording.")

bullet("Remembers when each person entered each zone. Per (zone, track_id), because one person "
       "can walk from a quiet zone into a busy one. Example: ID 7 enters at 9.0 s; at 12.4 s the "
       "dwell is 3.4 s.", "DwellTracker - ")
bullet("Estimates movement speed in PIXELS per second. Example: foot at (100,200) at 1.0 s, then "
       "(140,200) at 3.0 s gives 40 px in 2 s = 20 px/s.",
       "SpeedTracker - ")
bullet("Piles up foot points over time, decaying by HEAT_DECAY each frame, then blurs, "
       "normalises and masks. Example: 1.0 x 0.995^100 is about 0.61 after 100 frames.",
       "HeatmapAccumulator - ")
bullet("Fires only after 3 s of sustained over-capacity, clears only after 5 s back to normal. "
       "This is what stops one crowd producing dozens of alerts. Example: 4 s over capacity "
       "produces exactly one TRIGGERED.", "AlertDebouncer - ")

heading("app/db.py - 171 lines - the history", 3)
para("Why a separate module: the engine writes while the video runs and the API reads for the "
     "dashboard. Every SQL statement is in one file, so there is one place to look when a number "
     "seems wrong.")

table(
    ["Table", "Columns", "What one row means"],
    [
        ["alerts", "id, zone, source, started_at, video_ts, ended_at, peak_count, capacity, keyframe",
         "One over-capacity episode"],
        ["headcount", "ts, zone, count", "One sample every 2 video seconds"],
    ],
)

para("Three decisions worth defending:")
bullet("Every value is passed as a ? parameter, never formatted into the SQL string. A zone name "
       "is user data; formatting would allow SQL injection and break on any quote.",
       "Parameterised SQL: ")
bullet("Each function opens its own short-lived connection. SQLite objects cannot be shared "
       "between threads, and the engine runs in a different thread from FastAPI.",
       "A connection per call: ")
bullet("insert_alert returns the row id, because the evidence photo is named alert_<id>.jpg - "
       "the id must exist before the file can be named.", "Why insert returns an id: ")

heading("app/engine.py - 516 lines - the loop and the hand-over", 3)
para("The largest file, and the most likely to be probed. It has two jobs: run the video loop, "
     "and own SharedState.")

bullet("The heart of the architecture. set() replaces frame, people and snapshot under one lock; "
       "get() returns all three together. Why one lock: the video and the numbers must describe "
       "the same moment, or the boxes will not match the counts beside them.",
       "SharedState - ")
bullet("Returns a valid all-zero snapshot. A browser connects before YOLO has loaded; sending {} "
       "would break the contract and force every client to handle missing keys.",
       "empty_snapshot(source) - ")
bullet("Returns the .mp4 names in demo_videos/. Why an allow-list and not a path check: "
       "set_source must never accept a path from the browser, so only names this function "
       "returned can ever be accepted.", "list_clips() - ")
bullet("A daemon thread running while True: _play_clip(). Forever, because replaying the footage "
       "is more honest than freezing on the last frame. Wrapped in try/except so a crash does not "
       "leave a permanently frozen dashboard.", "Engine(threading.Thread) - ")
bullet("Everything that remembers (tracks, dwell, speed, heat, debouncers) is rebuilt here, so a "
       "replay starts clean instead of inheriting the last loop's state.", "_play_clip - ")
bullet("Assembles the exact dict the browser receives. Every number is cast to int/float because "
       "numpy scalars are not JSON-serialisable.", "_build_snapshot - ")
bullet("Builds one JPEG from the newest frame, drawing only what the query flags ask for.",
       "render(boxes, zones_on, heat) - ")

heading("app/main.py - 176 lines - the web layer", 3)
para("Why it is thin: all the thinking already lives in engine.py, db.py and zones.py. This file "
     "only translates HTTP requests into calls on those modules. A web bug is then always a web "
     "bug, never a detection bug.")

table(
    ["Route", "Returns", "Why it exists"],
    [
        ["GET /", "the dashboard HTML", "The page itself"],
        ["GET /video", "MJPEG stream", "Live video inside a plain <img> tag"],
        ["WS /ws", "snapshot JSON 2x/sec", "Live numbers"],
        ["GET /api/sources", "clip names", "Fills the source picker"],
        ["POST /api/source", "{\"ok\": true}", "Switches clips"],
        ["GET /api/zones", "polygons + capacities", "Draws the meters and the site plan"],
        ["GET /api/alerts", "newest alerts", "The alert feed"],
        ["GET /api/history", "headcount samples", "The line chart"],
    ],
)

heading("The web files", 3)

bullet("415 lines. Eight regions: sticky top bar, error bar, congestion banner, the readings "
       "strip, the console grid (camera + trend | occupancy + site plan + event log), footer, "
       "toast and evidence dialog. Plain HTML with Tailwind classes; no framework, no build step.",
       "static/index.html - ")
bullet("1957 lines in fourteen numbered sections. The jobs: helpers, fetching, KPIs, occupancy "
       "meters, the site plan, alerts, chart, live wiring, actions. The function most likely to "
       "be asked about is update(snapshot), the single entry point for live data.",
       "static/app.js - ")
bullet("1618 lines. Design tokens as CSS variables (--bg, --panel, --rule, --ink, --ok, --warn, "
       "--crit, --accent), the flat .glass panel surface with hairline rules, .tnum and .mono for "
       "tabular numbers so digits do not shift, status chips that pair colour with an icon, and a "
       "prefers-reduced-motion block. The look is an operations console, not a marketing "
       "dashboard: flat surfaces, square corners, colour only as a state signal.",
       "static/style.css - ")

heading("Why it looks like this, and not like a dashboard", 3)

para("This matters because the interface is the largest part of the assessment, and \"it looks "
     "modern\" is not an answer. Every choice below exists to help someone watching a screen for "
     "an hour, and each is one you can defend in a sentence.")

bullet("The brief is about a crowd, so the video is the biggest thing on the page, not a tile "
       "among four. The camera panel takes eight of twelve columns.", "The camera dominates: ")
bullet("Four numbers in one bordered strip rather than four floating cards. Four separate boxes "
       "compete with the video for attention, and a strip takes half the height.", "One readings strip: ")
bullet("A bar per zone, not a ring. Capacity is a comparison against a limit; a bar shows how much "
       "of the limit is used, while a ring makes the reader estimate an angle.",
       "Occupancy is bars: ")
bullet("The site plan draws the real zone polygon from zones.json and zooms to fit it, with one "
       "dot per counted person. An operator recognises their own area, and the plan cannot drift "
       "from the video overlay because both read the same coordinates.",
       "The site plan: ")
bullet("Colour is a state signal, not decoration. Everything is grey until a zone reaches 80 "
       "percent of capacity (amber) or goes over it (red). A page that is colourful everywhere "
       "has nowhere to put an alarm.", "Colour means something: ")
bullet("Numbers are set in a monospace face with tabular figures, so a digit changing from 1 to 7 "
       "does not shift the layout. Units are small and beside the number, the way a control panel "
       "is labelled.", "Numbers look like readings: ")
bullet("Flat surfaces, hairline rules, 4-pixel corners and no soft shadows. This style is borrowed "
       "from control-room software rather than consumer apps, and it stays legible on a dim "
       "projector, where a soft shadow turns to mud.", "The finish: ")
bullet("The layout is a 12-column grid that collapses to one column on a phone, and the readings "
       "strip goes from four cells to two. Nothing scrolls sideways at any width.",
       "It is responsive: ")

heading("The supporting files", 3)

bullet("23 lines. One \"Main Zone\" per clip, capacities 4 / 5 / 4. Why JSON: zones are data, "
       "not logic, so an operator can change a polygon without touching Python.",
       "zones.json - ")
bullet("185 lines, 20 tests in data-flow order: person, zone, analytics, database, shared state, "
       "clips. Why one file instead of six: one file read top to bottom is far easier to walk a "
       "panel through.", "tests/test_pipeline.py - ")
bullet("23 lines. Activates .venv, opens the browser after 4 seconds, starts uvicorn on "
       "127.0.0.1:8000.", "start.bat - ")
bullet("Pinned versions. Python 3.10 to 3.12 - 3.13 is not supported by the pinned build.",
       "requirements.txt - ")

pagebreak()

# =============================================================================================
# PART 3 - HOW IT WORKS
# =============================================================================================

heading("Part 3 - How it works, frame by frame", 1)

para("This is the sequence to narrate if asked \"walk me through what happens when a person "
     "appears\". Follow one frame:")

code("""frame arrives                      frame_index 240
   │
   ├─ every STRIDE'th frame only ────  STRIDE 2, so analyse 240, skip 241
   ├─ resize to 640 wide ──────────── 1280x720 becomes 640x360
   ├─ detector.track(frame) ───────── YOLO finds people, ByteTrack assigns IDs
   │                                   -> [Person(7, box, 0.91, foot=(120,200)), ...]
   ├─ now = frame_index / fps ─────── 240 / 29.97 = 8.01 s of VIDEO time
   ├─ count_by_zone(zones, people) ── feet in "Main Zone" -> [p7, p9]
   ├─ dwell.update(now, members) ──── remember when ID 7 entered the zone
   ├─ speeds.update(now, people) ──── distance moved / time since last seen
   ├─ heatmap.add(feet) ───────────── add 1.0 at each foot pixel
   ├─ debouncer.update(...) ───────── over capacity for 3 s? -> raise an alert
   ├─ every 2 video seconds ───────── write headcount rows to SQLite
   └─ state.set(frame, people, heat, snapshot)  published under one lock
                   │
                   ├──> WebSocket sends the snapshot 2x per second
                   └──> /video renders a JPEG up to 15x per second""")

heading("The one idea that makes the architecture work", 2)

para("Reading a frame and running YOLO takes about 60 to 110 milliseconds. A browser asking for "
     "the latest numbers must be answered in microseconds. If a web request did the vision work, "
     "the page would freeze.")

table(
    ["Thread", "Job", "Speed"],
    [
        ["Engine (background)", "read frame, detect, count, save, publish", "~10-16 frames/second"],
        ["Web (FastAPI)", "serve whatever the engine last published", "instant"],
    ],
)

para("They meet only at SharedState, protected by one lock. The engine writes; web requests read "
     "copies. No request ever waits for the model. That is the whole trick, and it is worth "
     "saying out loud in the interview.")

heading("Why video time and not the wall clock", 2)
para("Every analytics number uses frame_index / fps - video time - not time.time(). The demo "
     "replays a recording at roughly 16 fps, but the recording itself is 29.97 fps. If dwell used "
     "the wall clock, a person standing still for 10 seconds of video would report about 18 "
     "seconds of dwell, and the 3-second alert delay would be wrong too.")

pagebreak()

# =============================================================================================
# PART 4 - THE NUMBERS
# =============================================================================================

heading("Part 4 - The numbers, with the arithmetic", 1)

para("Panels like concrete arithmetic. These are the worked examples that actually appear in the "
     "app, and each one is short enough to say out loud.")

heading("Counts and fill", 2)
bullet("7 people in a capacity-4 zone gives fill 7/4 = 1.75, status OVER.", "Over capacity: ")
bullet("The occupancy bar is clamped to 1.0, so it fills its track exactly; the OVER chip and the "
       "\"over 3 s\" note carry the excess.", "The bar: ")
bullet("3 in a capacity-4 zone gives 0.75, and 0.75 is below 0.8, so status is OK.", "Under capacity: ")
bullet("4 in a capacity-4 zone gives 1.0, which is 80% or more, so status is NEAR, not OVER.", "Exactly full: ")

heading("Dwell time", 2)
bullet("ID 7 enters at video 9.0 s; at 12.4 s the dwell is 12.4 - 9.0 = 3.4 s.", "One person: ")
bullet("Nine people at 2 s and one at 60 s give an average of (18 + 60) / 10 = 7.8 s, but a "
       "maximum of 60 s. The average hides the problem; the maximum reveals it.",
       "Why both average and max: ")

heading("Movement speed", 2)
bullet("Foot at (100,200) at 1.0 s, then (140,200) at 3.0 s. Distance 40 px, elapsed 2 s, so 20 px/s.", "Straight line: ")
bullet("(0,0) to (30,40) is sqrt(900 + 1600) = 50 px, not 70. Pythagoras matters for diagonal movement.", "Diagonal: ")

heading("Heatmap decay", 2)
bullet("1.0 x 0.995^1 = 0.995")
bullet("1.0 x 0.995^10 = about 0.951")
bullet("1.0 x 0.995^100 = about 0.61")

heading("Alert timing", 2)
bullet("Over capacity at 0, 1, 2 and 3 s fires at the 3 s call. It stays quiet at 4 s because the "
       "alert is already active.", "ON_DELAY 3 s: ")
bullet("Back under capacity at 4 s means the alert clears at 9 s.", "OFF_DELAY 5 s: ")

heading("Measured performance on this laptop", 2)
para("11th Gen Intel i3-1125G4, 4 physical cores, no GPU:")
bullet("16.6 / 16.1 / 15.9 fps for crowded / mid / normal.", "Sustained: ")
bullet("14.98 fps is needed to keep up with STRIDE 2 at 29.97 fps, so all three run faster than "
       "real-time-equivalent.", "Required: ")
bullet("79 to 86 ms.", "p95 frame time: ")
bullet("About 78 to 79% of each frame. Detection is the dominant cost.", "detect + track share: ")

callout("If asked about accuracy",
        "Be specific and honest: YOLOv8 nano misses some small or distant people, so counts are a "
        "lower bound in very wide shots. A larger model is more accurate but would not hold real "
        "time on this CPU. That is a measured trade-off, not a bug.")

pagebreak()

# =============================================================================================
# PART 5 - HOW TO RUN
# =============================================================================================

heading("Part 5 - How to run it", 1)

heading("The one-step way (use this for the demo)", 2)
para("Double-click start.bat in the project folder. Or, from PowerShell:")
code("cd C:\\Users\\akshaya\\Downloads\\crowd-analytics\n.\\start.bat")
para("What it does, in order: activates the virtual environment, opens your browser after 4 "
     "seconds, and starts the server on 127.0.0.1:8000. Leave the black window open - closing it "
     "stops the app.")

heading("The manual way (if you need to see logs)", 2)
code("cd C:\\Users\\akshaya\\Downloads\\crowd-analytics\n"
     ".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
para("Then open http://127.0.0.1:8000 in a browser. The first startup takes 10 to 20 seconds "
     "while YOLO loads.")

heading("Stopping it", 2)
para("Press Ctrl+C in the terminal window, or close it. If a stale process is holding the port:")
code("Get-Process python | Where-Object { $_.Path -like \"*crowd-analytics*\" } | Stop-Process -Force")

heading("Running the tests", 2)
code("cd C:\\Users\\akshaya\\Downloads\\crowd-analytics\n"
     ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v")
para("Expected: Ran 20 tests ... OK. This takes under a second and proves the geometry, analytics "
     "and database logic without needing the model.")

heading("Rebuilding the environment from scratch", 2)
para("Only needed on a new machine:")
code("py -3.12 -m venv .venv\n"
     ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
para("Python 3.13 is not supported by the pinned dependencies. Use 3.10 to 3.12.")

heading("What each file under the hood is for", 2)
table(
    ["To change...", "Edit this"],
    [
        ["A detection threshold or timing", "app/config.py"],
        ["Where a zone is, or how full it may get", "zones.json"],
        ["How the video is drawn", "app/engine.py, render()"],
        ["What the dashboard shows", "static/app.js"],
        ["Colours, spacing, typography", "static/style.css"],
        ["An API route", "app/main.py"],
    ],
)

callout("If the port is busy",
        "Change --port 8000 to --port 8123 in the command above, and open "
        "http://127.0.0.1:8123 instead. Note that start.bat hardcodes 8000.", CRIT)

pagebreak()

# =============================================================================================
# PART 6 - THE DEMO
# =============================================================================================

heading("Part 6 - How to demo it", 1)

para("Rehearse this twice. The only timing risk is the first alert, which needs about 35 seconds "
     "of video before it appears - know what you will say while waiting.")

callout("Before you start",
        "Open the dashboard in a fresh tab and close every other tab. Each open tab holds its own "
        "video stream and starves the CPU, which makes the video look black. This is the most "
        "common way to fail the demo.")

heading("The 3-minute script", 2)

numbered("Start on crowded.mp4. \"This is the live camera. The green boxes are detections, and the "
         "red polygon on the video is the monitored zone, currently over capacity at 6 out of 4.\"")
numbered("Point at the readings strip. \"People now, peak this session, average dwell, and the "
         "actual processing rate on this machine - about 16 frames a second on a CPU, no GPU.\"")
numbered("Point at the occupancy panel. \"One bar per zone. The bar is how far the zone is towards "
         "its capacity, and the number on the right is the count against that capacity. This one "
         "reads OVER, and below the bar are the average dwell and the speed in pixels per second.\"")
numbered("Point at the site plan. \"The same polygon as on the video, drawn to scale from "
         "zones.json, with one dot per counted person. It turns amber at 80 percent of capacity and "
         "solid red when over, so the plan alone says where the problem is.\"")
numbered("Wait for the alert. \"The banner fires because this zone has been over capacity for "
         "three continuous seconds. A single bad detection cannot trigger it - that is the "
         "debouncer.\"")
numbered("Click the alert in the log. \"The app saved the exact frame that caused it, with the "
         "boxes and zones drawn in. That is the evidence.\"")
numbered("Switch to normal.mp4 in the dropdown. \"Same pipeline, low density. Watch: no alert. "
         "That is the false-positive test - an empty scene must not set off the alarm.\"")
numbered("End on the chart. \"This is headcount over time, with the capacity line drawn across it, "
         "so you can see exactly when the crowd crossed the threshold.\"")

heading("Things to toggle while talking", 2)

bullet("Turns the detection boxes off, so the crowd is visible underneath.", "Boxes chip: ")
bullet("Turns the zone polygon off, to show the raw footage.", "Zones chip: ")
bullet("Turns on the density heatmap - where people keep standing over time. This is the "
       "\"density heatmap\" requirement in the brief.", "Heatmap chip: ")
bullet("Expands the video to full screen if the panel is far away.", "Fullscreen button: ")

heading("If something goes wrong", 2)
table(
    ["Symptom", "What to do"],
    [
        ["Video area is black", "Close other tabs; the CPU is starved. Reload the page."],
        ["No alert after 40 s", "The clip loops; it fires next pass at ~31 s. Keep talking."],
        ["Page will not load", "Check the terminal is open with no traceback. A busy port "
                               "means a server is already running: stop it, or use --port 8123."],
        ["Live pill says Reconnecting", "The WebSocket dropped; it retries within a few seconds."],
    ],
)

pagebreak()

# =============================================================================================
# PART 7 - INTERVIEW ANSWERS
# =============================================================================================

heading("Part 7 - Interview answers", 1)

heading("The technical questions", 2)

qa = [
    ("Walk me through what happens when I open the page.",
     "The browser loads index.html, then calls /api/sources, /api/zones, /api/history and "
     "/api/alerts, and opens /ws. It then points the <img> at /video. Meanwhile the engine thread "
     "is already looping over the clip. Every 0.5 s the WebSocket pushes a snapshot and the page "
     "re-renders the readings strip, the meters, the site plan and the chart. The <img> receives a "
         "new JPEG up to 15 times a second."),
    ("Why is the vision work in a separate thread?",
     "Because vision is slow - 60 to 110 ms per frame - and the web must be instant. One thread "
     "does the slow work and publishes its result; requests read the last published result under "
     "one lock. That is why the dashboard never freezes while the model is thinking."),
    ("Why one lock and not one per piece of data?",
     "The video and the numbers must describe the same moment. With separate locks a page could "
     "show a frame from video-second 10.0 beside a count from 10.5 s, and the boxes would not "
     "match the numbers. get() returns frame, people and snapshot together inside one locked "
     "block, so they are always consistent."),
    ("Why the bottom-centre of the box and not the centre?",
     "A box's centre sits around the person's chest, which floats up and down as they walk. The "
     "feet sit on the floor, and zone polygons are drawn on floor areas. So the foot point is the "
     "only position that answers \"is this person inside this area?\" correctly."),
    ("Why ByteTrack, and not a simpler tracker?",
     "It ships inside ultralytics, so it adds no dependency, and it is designed for exactly this: "
     "stable IDs through brief occlusion at video rates. It keeps working when the detector misses "
     "a frame, which matters because STRIDE 2 already skips every second frame."),
    ("Why analyse only every second frame?",
     "It roughly doubles throughput. At a 29.97 fps source, every second frame still gives about "
     "15 analyses per second - far more than the 2 per second the dashboard needs. And because "
     "dwell and alert timing use TIME rather than frame counts, skipping frames does not break them."),
    ("Why pixels per second for speed, and not km/h?",
     "Converting pixels to metres needs a camera calibration - where the floor is, how far away, "
     "at what angle. We do not have that, so any km/h figure would be invented. Pixels per second "
     "is honest and still answers the operational question: a zone where people move at 5 px/s is "
     "far more congested than one where they move at 40 px/s."),
    ("Why does the alert wait 3 seconds?",
     "The head count flickers by plus or minus one constantly, because a detection misses or "
     "someone steps on a line. Alerting on the raw signal would produce dozens of alerts for one "
     "real crowd. Three seconds of sustained over-capacity ignores a blip and is still fast enough "
     "to be useful."),
    ("Why 5 seconds to clear?",
     "An alert must not flicker off the moment one person steps out. Five seconds of sustained "
     "normal traffic means the crowd really has dispersed."),
    ("How do you know it does not produce false alerts?",
     "normal.mp4, the low-density clip, runs a full loop and produces zero alerts, while "
     "crowded.mp4 produces exactly the expected one. That is the false-positive test, and it is "
     "documented in demo_videos/expected_results.md."),
    ("Why MJPEG instead of WebRTC?",
     "WebRTC needs signalling, STUN/TURN and a codec pipeline - a lot of machinery to display a "
     "640x360 stream on localhost. MJPEG renders inside a plain <img> tag with no JavaScript and "
     "no extra dependency. The bandwidth cost does not matter on loopback."),
    ("Why is the front end plain HTML instead of React?",
     "The brief asks for no build step. Plain HTML plus Tailwind plus Chart.js loads instantly, has "
     "no toolchain to break before a demo, and every line is readable in the browser. The whole UI "
     "is three files."),
    ("Why are zones in a JSON file?",
     "Zones are configuration, not code. An operator can redraw a polygon or change a capacity "
     "without touching Python - and no magic number ends up hidden inside a function."),
    ("What happens if the model misses a person?",
     "Two safeguards. ByteTrack keeps a track alive for 2 seconds, so a one-frame miss does not "
     "reset the dwell clock. And the debouncer requires 3 seconds of sustained over-capacity, so a "
     "single missed detection cannot fire an alert."),
    ("What if the video file is missing at startup?",
     "The loop raises a clear error, catches it, prints the reason and retries after a second. The "
     "web server stays up and the dashboard shows an error bar instead of a crash."),
    ("How fast is it, and can you prove it?",
     "About 16 fps sustained on this 4-core laptop with no GPU, measured as a moving average over "
     "20 frames and displayed live in the Processing FPS tile. Detection and tracking account for "
     "78 to 79 percent of each frame."),
]

for question, answer in qa:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(f'"{question}"')
    run.bold = True
    run.font.color.rgb = ACCENT
    para(answer)

heading("The questions you must not bluff", 2)

callout("Did you record the demo footage yourself?",
        "No - say it directly. The three clips are openly licensed stock footage from Pexels, and "
        "demo_videos/SOURCES.csv records the original URL, author and licence for each. What is "
        "custom is everything around them: the three density levels, the zone polygons drawn for "
        "each camera angle, the capacities tuned so one clip alerts and two do not, and the "
        "measured expected-results table.", CRIT)

callout("Is this your own code?",
        "Answer by explaining it, not by defending it. Point at a specific decision - why the foot "
        "point is bottom-centre, why the alert waits 3 seconds, why there is one lock - and explain "
        "the trade-off. Anyone who can explain the reasoning wrote or fully understands the code.",
        CRIT)

pagebreak()

# =============================================================================================
# PART 8 - LIMITATIONS
# =============================================================================================

heading("Part 8 - Limitations, and how to say them", 1)

para("State these before you are asked. An applicant who knows the limits of their own build "
     "scores better than one who claims there are none.")

table(
    ["Limitation", "How to say it"],
    [
        ["Nano misses small or distant people",
         "Counts are a lower bound in wide shots. A larger model is more accurate but would not "
         "hold real time on this CPU - a measured trade-off."],
        ["Speed is pixels, not metres",
         "No camera calibration, so km/h would be invented. Px/s is honest and comparable within "
         "one clip."],
        ["One zone per clip in the demo",
         "The code supports any number; the demo keeps one so the story stays simple."],
        ["No identity or re-identification",
         "A track ID is not a person's identity, and IDs reset between clips."],
        ["CPU only, about 16 fps",
         "Enough for the dashboard's 2-per-second updates; a GPU would allow a larger model."],
        ["Zone polygons are static",
         "A moving camera would need them redrawn - which is why zones are per clip."],
        ["Heatmap is foot density",
         "It shows where people stand, not people per square metre, because there is no "
         "calibration."],
        ["Footage is Pexels stock",
         "Credited in SOURCES.csv. The zone tuning, capacity choice and expected results are ours."],
    ],
)

heading("What you would do with more time", 2)
numbered("Add a calibration step so speed can be reported in metres per second.")
numbered("Add a zone editor in the UI, instead of editing zones.json by hand.")
numbered("Cache detection results per frame so replaying a clip does not re-run the model.")
numbered("Add a second zone per clip to demonstrate multi-zone bottlenecks.")

pagebreak()

# =============================================================================================
# APPENDIX
# =============================================================================================

heading("Appendix - Last-minute checklist", 1)

para("Run through this the morning of the interview.")

numbered("The five links and commands below all work on this machine, today.")
numbered("The dashboard opens and shows live video with boxes within 10 seconds.")
numbered("An alert appears on crowded.mp4 within about 40 seconds.")
numbered("Switching to normal.mp4 produces no alert.")
numbered("You can say the 30-second pitch from Part 1 without reading it.")
numbered("You can name what config.py, vision.py, zones.py, analytics.py, engine.py and main.py do.")
numbered("You have decided how you will answer the Pexels question.")

heading("The exact commands", 2)
code("cd C:\\Users\\akshaya\\Downloads\\crowd-analytics\n"
     ".\\start.bat\n\n"
     "# tests\n"
     ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests\n\n"
     "# manual start\n"
     ".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000")

heading("The links", 2)
table(
    ["What", "Where"],
    [
        ["The running app", "http://127.0.0.1:8000"],
        ["GitHub repository", "https://github.com/nithyaa021/crowd-analytics"],
        ["Long-form code walkthrough", "CODE_GUIDE.md in the project folder"],
        ["Expected results per clip", "demo_videos/expected_results.md"],
        ["Architecture diagram", "docs/architecture.png"],
    ],
)

doc.add_paragraph()
para("Good luck. You built a working system, you can explain every line of it, and you know its "
     "limits. That is what the panel is actually testing.", bold=True)

# ---- save -----------------------------------------------------------------------------------
OUT.parent.mkdir(exist_ok=True)
doc.save(OUT)
size_kb = OUT.stat().st_size / 1024
print(f"wrote {OUT}  ({size_kb:.0f} KB)")
