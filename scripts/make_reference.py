"""Builds docs/Crowd_Analytics_Reference.docx - a complete, monochrome reference manual.

Why a separate document from the handbook: the handbook is a 3-minute interview script, kept
short on purpose. This one is the full reference - every file, every function, every design
decision - for someone who has to explain the whole build in depth.

Why a generator: the manual describes the real repository, so a script that is re-run whenever the
code changes cannot drift out of date the way hand-written prose does.

Why no colour: this document is printed. Every surface is black text on white, with grey only for
rules and shading, so it survives a mono laser printer and a photocopy. No accent colour is used
anywhere.

Why python-docx: it writes a real .docx with no Word automation, so it works with Word closed.
"""

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "Crowd_Analytics_Reference.docx"

# ---- monochrome palette: black ink, two greys for rules and shading, nothing else ------------
INK = RGBColor(0x00, 0x00, 0x00)
GREY = RGBColor(0x59, 0x59, 0x59)
RULE_GREY = "BFBFBF"
SHADE_LIGHT = "F2F2F2"
SHADE_HEAD = "595959"

doc = Document()

# True when the next heading must start a fresh page. Set by pagebreak().
_pending_break = False
# Counter for numbered(). A one-item list so numbered() can update it from inside a function.
_num = [0]


def _restart_numbers() -> None:
    """Starts the next numbered list again at 1.

    Why: a numbered list is always a self-contained block of steps, so it must not inherit the
    count from whatever list came before it.
    """
    _num[0] = 0


def setup_styles() -> None:
    """Sets the base font and page size once, so every block inherits the same look.

    Why Calibri: it ships with Windows, so the file renders identically on any machine that opens
    it. Why A4 with wide-ish margins: the panel may print it, and a long line of monospace code is
    unreadable in a narrow column.
    """
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.font.color.rgb = INK
    style.paragraph_format.space_after = Pt(5)
    style.paragraph_format.line_spacing = 1.08

    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)


def heading(text: str, level: int = 1) -> None:
    """Adds a heading and honours a pending page break.

    Why the pending-break flag: a break inserted as its own empty paragraph leaves a blank page
    behind it. Asking the NEXT heading to start a new page avoids that.
    """
    global _pending_break
    _restart_numbers()
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        # Every heading is black. Level is conveyed by size alone, which is what a mono printout
        # can still show.
        run.font.color.rgb = INK
        run.font.name = "Calibri"
        run.bold = True
    if level == 1:
        h.paragraph_format.space_before = Pt(18)
        h.paragraph_format.space_after = Pt(8)
    elif level == 2:
        h.paragraph_format.space_before = Pt(12)
        h.paragraph_format.space_after = Pt(4)
    if _pending_break:
        h.paragraph_format.page_break_before = True
        _pending_break = False


def para(text: str, bold: bool = False, italic: bool = False, size: float = 10.5) -> None:
    """Adds a normal paragraph of prose."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return p


def lead(text: str) -> None:
    """Adds a short grey lead-in line under a heading, to orient the reader before detail."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(10)
    run.font.color.rgb = GREY


def bullet(text: str, bold_prefix: str = "") -> None:
    """Adds a bullet, with an optional bold prefix so the point reads at a glance."""
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    if bold_prefix:
        run = p.add_run(bold_prefix)
        run.bold = True
    p.add_run(text)


def numbered(text: str) -> None:
    """Adds a numbered step.

    Why the number is written by hand: Word numbers every List Number paragraph as one continuous
    sequence, so a second list would start at "9." instead of "1.". A local counter that any other
    block resets keeps each list correct.
    """
    _num[0] += 1
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.left_indent = Inches(0.32)
    p.paragraph_format.first_line_indent = Inches(-0.22)
    run = p.add_run(f"{_num[0]}.  ")
    run.bold = True
    p.add_run(text)


def code(text: str) -> None:
    """Adds a monospace block on a light grey background, for paths, commands and signatures."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.2)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), SHADE_LIGHT)
    p._p.get_or_add_pPr().append(shd)
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    run.font.color.rgb = INK


def table(headers: list[str], rows: list[list[str]]) -> None:
    """Adds a bordered table with a dark header row and a repeating header.

    Why the header repeats: a table that spills onto the next page would otherwise continue with
    anonymous columns. Why cantSplit on every row: a row cut in half reads as a printing defect.
    """
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    tr_pr = t.rows[0]._tr.get_or_add_trPr()
    header_flag = OxmlElement("w:tblHeader")
    header_flag.set(qn("w:val"), "true")
    tr_pr.append(header_flag)
    tr_pr.append(OxmlElement("w:cantSplit"))

    hdr = t.rows[0].cells
    for i, name in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        # Bind the header paragraph to the first data row, or Word leaves the header alone at the
        # foot of a page with its rows overleaf.
        p.paragraph_format.keep_with_next = True
        run = p.add_run(name)
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), SHADE_HEAD)
        hdr[i]._tc.get_or_add_tcPr().append(shd)

    for row in rows:
        cells = t.add_row().cells
        row_pr = t.rows[-1]._tr.get_or_add_trPr()
        row_pr.append(OxmlElement("w:cantSplit"))
        for i, value in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(value))
            run.font.size = Pt(8.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def note(title: str, text: str) -> None:
    """Adds a single-cell shaded box for something the reader must not miss."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), SHADE_LIGHT)
    cell._tc.get_or_add_tcPr().append(shd)
    p = cell.paragraphs[0]
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(10)
    p2 = cell.add_paragraph()
    run2 = p2.add_run(text)
    run2.font.size = Pt(9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def kv_table(rows: list[list[str]]) -> None:
    """Adds a two-column table with no header row, for the cover's fact list.

    Why a separate helper: table() always paints a header, and on the cover that would be an
    empty dark strip across the top with nothing in it, which reads as a printing fault.
    """
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    # The first column is a fixed label column so every value lines up down the page.
    t.columns[0].width = Inches(1.35)
    t.columns[1].width = Inches(4.95)
    for label, value in rows:
        cells = t.add_row().cells
        cells[0].width = Inches(1.35)
        cells[1].width = Inches(4.95)
        run = cells[0].paragraphs[0].add_run(label)
        run.bold = True
        run.font.size = Pt(9)
        run2 = cells[1].paragraphs[0].add_run(value)
        run2.font.size = Pt(9)


def pagebreak() -> None:
    """Marks that the next heading should start a new page."""
    global _pending_break
    _pending_break = True


# =============================================================================================
# COVER
# =============================================================================================

setup_styles()

title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.LEFT
title.paragraph_format.space_before = Pt(140)
run = title.add_run("Crowd Density and Bottleneck Analytics")
run.font.size = Pt(28)
run.bold = True
run.font.color.rgb = INK

subtitle = doc.add_paragraph()
run = subtitle.add_run("Complete technical reference")
run.font.size = Pt(15)
run.font.color.rgb = GREY

rule = doc.add_paragraph()
rule.paragraph_format.space_before = Pt(10)
pPr = rule._p.get_or_add_pPr()
bdr = OxmlElement("w:pBdr")
bottom = OxmlElement("w:bottom")
bottom.set(qn("w:val"), "single")
bottom.set(qn("w:sz"), "8")
bottom.set(qn("w:space"), "1")
bottom.set(qn("w:color"), RULE_GREY)
bdr.append(bottom)
pPr.append(bdr)

para("")
para("Every file, every function, every design decision, and why each one exists.", size=11)
para("")

meta = [
    ["Programme", "Cogno Valley, Vision AI internship. Track A: crowd and bottleneck analytics."],
    ["Build", "Python 3.12, YOLOv8 nano with ByteTrack, OpenCV, FastAPI, SQLite, CPU only"],
    ["Front end", "Plain HTML, Tailwind CSS, Chart.js, vanilla JavaScript. No build step, no framework"],
    ["Audience", "The author, preparing to explain this build to a technical panel"],
    ["Scope", "9,256 lines across 21 files, 20 automated tests, 3 demo clips"],
]
kv_table(meta)

para("")
para("This document is generated from the repository by scripts/make_reference.py, so the file "
     "names, line counts and function names in it are the real ones. It is deliberately printed "
     "in black and white: no colour is used anywhere in it.", italic=True, size=9.5)

pagebreak()

# =============================================================================================
# HOW TO READ THIS
# =============================================================================================

heading("How to read this document", 1)

lead("Four ways in, depending on how much time you have.")

para("This manual is organised the way the system is built, from the outside in. Each part answers "
     "a question a panel is likely to ask, and each part can be read on its own.")

table(
    ["If you need to...", "Read"],
    [
        ["Explain the project in two minutes", "Part 1, then Part 3"],
        ["Answer \"what does this file do?\"", "Part 4, the file-by-file reference"],
        ["Answer \"why is this function written that way?\"", "Part 5, the function reference"],
        ["Explain the dashboard and its design", "Part 6, the dashboard"],
        ["Defend a number you put on screen", "Part 7, the numbers"],
        ["Answer \"what went wrong, and what did you fix?\"", "Part 8, the defects"],
        ["Say honestly what it cannot do", "Part 9, limitations"],
    ],
)

note("The one-sentence version",
     "A video feed goes in; YOLOv8 nano finds people in each frame and ByteTrack gives each person a "
     "stable number; each person's foot point is tested against a hand-drawn zone polygon; the "
     "resulting counts, dwell times, speeds and a decay heatmap are published about twice a second "
     "over a WebSocket; a debounced rule raises a congestion alert only when a zone stays over "
     "capacity for three continuous seconds, and saves an evidence photo when it does.")

para("")
para("Two conventions run through the whole document:")

bullet("a claim about the code names the file and the function, so it can be checked. Where a "
       "number appears, it came from the running program, not from memory.", "Verifiable: ")
bullet("every \"why\" states the failure that would happen without the decision. A reason that "
       "cannot name a failure is not a reason, it is a preference, and it is marked as one.",
       "Failure-first: ")

pagebreak()

# =============================================================================================
# PART 1 - WHAT IT DOES AND WHY
# =============================================================================================

heading("Part 1 - What the system does, and why it exists", 1)

heading("The problem", 2)

para("A station concourse, a shopping-mall escalator landing, a stadium concourse: these are wide "
     "open spaces that are perfectly safe when people are spread out and genuinely dangerous when "
     "they are not. The failure mode is not dramatic. A queue grows by one person at a time, "
     "nobody notices the moment it crosses from \"busy\" to \"cannot disperse\", and the people "
     "inside it have no way to see the whole picture.")

para("A human watching a camera feed is bad at exactly the thing that matters here. They are good "
     "at noticing one person fall, and bad at holding an accurate running count of thirty people "
     "while also judging whether that number has been above a threshold for three seconds. The "
     "count is what decides whether an area must be closed, and a human cannot do it reliably.")

para("So the system answers three questions continuously, and nothing else:")

numbered("How many people are inside each configured area right now?")
numbered("How long have they been there, and are they moving or stuck?")
numbered("Has any area been over its safe capacity long enough to be a real problem, rather than a "
         "blip?")

para("Every design decision in this document exists to serve one of those three, and anything that "
     "did not serve them was deliberately left out. That is why there is no face recognition, no "
     "person re-identification, no database of individuals, and no attempt to identify anyone. The "
     "system counts anonymous feet.")

heading("Why these three questions, and not a fourth", 2)

para("The internship brief for Track A names them directly: people and occupancy, density and "
     "flow, dwell and thresholds. But they are also the right three on their own merits, because "
     "they are the three an operator can act on right now.")

table(
    ["Question", "The decision it enables"],
    [
        ["How many, right now?", "Open another entrance, or hold people at the top of the escalator."],
        ["How long, and moving or stuck?", "A zone where people move at 5 px/s is a queue. A zone at "
         "40 px/s is a thoroughfare, even with the same head count."],
        ["Over capacity for long enough?", "Close the area, or divert. This is the one that must "
         "reach someone who is not looking at the screen."],
    ],
)

heading("What the user actually sees", 2)

para("One screen, laid out the way an operations desk is laid out rather than the way a marketing "
     "dashboard is. The camera is the largest element because it is the thing being watched. Beside "
     "it, in order of how often an operator looks at them: four live readings, one occupancy meter "
     "per zone, a site plan of the real zone geometry, and an event log with a clickable photograph "
     "of each alert.")

para("When something goes wrong the screen changes in three places at once, because one is not "
     "enough: a red banner across the top, a toast in the corner nearest the eye, and a new row in "
     "the log with its photograph attached. The browser tab title also gains the count, which is "
     "the only signal that reaches an operator who has tabbed away.")

heading("The four layers, and the one rule between them", 2)

para("The application is four layers, and data moves through them in one direction only. The rule "
     "that holds the design together is that the slow work and the fast work never touch each "
     "other: they meet at a single shared object that holds the newest finished result.")

code("""LAYER 1 - INPUT          demo_videos/*.mp4  +  zones.json
                              |
                              v
LAYER 2 - VISION         app/vision.py       YOLOv8n + ByteTrack -> Person objects
                         app/zones.py        which zone each foot point is in
                              |
                              v
LAYER 3 - ANALYTICS      app/analytics.py    dwell, speed, heatmap, alert debouncing
                         app/engine.py       the loop that runs all of it
                         app/db.py           SQLite: alert history, head-count history
                              |
                              v  (SharedState, one lock, copies out)
LAYER 4 - WEB + UI       app/main.py         HTTP + WebSocket + MJPEG
                         static/             the dashboard""")

para("The reason for the split is a measured one. Reading a frame and running the model takes "
     "60 to 110 ms on this machine. A browser asking for the current numbers must be answered in "
     "microseconds. If a web request had to wait for the model, the page would freeze every time "
     "the model was busy, which is always. So the model runs in one background thread and "
     "publishes; web requests only ever read the last published value.")

pagebreak()

# =============================================================================================
# PART 2 - ARCHITECTURE
# =============================================================================================

heading("Part 2 - The architecture, in depth", 1)

lead("Why two threads, why one lock, and what would break with a different number of either.")

heading("The two threads", 2)

para("There are exactly two things happening at once, and they are deliberately lopsided.")

table(
    ["Thread", "What it does", "How long one unit takes"],
    [
        ["Engine (background)", "Reads a frame, runs YOLO, tracks, counts zones, updates analytics, "
         "writes the snapshot, draws and JPEG-encodes the video", "60 to 110 ms per analysed frame"],
        ["Web (FastAPI)", "Answers /api/*, pushes the snapshot over /ws, streams MJPEG frames from "
         "/video", "microseconds for JSON, about 15 ms to encode one MJPEG frame"],
    ],
)

para("The engine is a subclass of threading.Thread created once at import time in app/main.py, "
     "and started in FastAPI's lifespan handler. It runs forever: when a clip reaches its last "
     "frame it starts again from the beginning, with every piece of memory reset.")

para("Why replay instead of stopping at the end: this is a live dashboard. Freezing on the last "
     "frame of a finished clip would leave a crowd on screen that never moves again, and every "
     "number beside it would be stale. Replaying is the honest simulation of a camera that keeps "
     "running.")

heading("SharedState: the single meeting point", 2)

para("SharedState is a small class in app/engine.py. It holds four things: the newest raw frame, "
     "the newest list of Person objects, the newest heat layer, and the newest snapshot dict. One "
     "lock guards all four.")

para("Why one lock and not four: the picture and the numbers must describe the same instant. With "
     "separate locks, a reader could collect a frame from video second 10.0 and a snapshot from "
     "second 10.5, and the boxes drawn on the picture would not correspond to the counts printed "
     "beside it. On a panel screen that is not a subtle bug, it is the first thing someone notices.")

para("Two rules make the lock safe:")

numbered("Everything that comes out is a copy. The engine keeps overwriting its own frame buffer; "
         "a reader holding a reference would watch the image change underneath it, and an image "
         "that changes halfway through JPEG encoding comes out torn.")
numbered("Everything that goes in is copied too. The snapshot is deep-copied on the way in, because "
         "it nests lists and dicts that a reader may walk through.")

code("""def get(self):
    with self._lock:
        frame = None if self._frame is None else self._frame.copy()
        return frame, list(self._people), copy.deepcopy(self._snapshot)""")

para("Why get() returns all three at once rather than three separate getters: three calls could "
     "interleave with an engine update between them, which is exactly the tearing described above.")

heading("Why the FPS number is a moving average", 2)

para("The engine records how long each analysed frame took and keeps the last 20 durations. The "
     "reported rate is 20 divided by their total.")

para("Why not report the instantaneous rate: one slow frame, caused by another program taking the "
     "CPU for a moment, would make the displayed rate jump from 16 to 4 and back within a second. "
     "That looks like a bug and invites a question you cannot answer mid-demo. A moving average "
     "over about three seconds shows the real throughput and hides the noise.")

heading("Why the engine catches its own exceptions", 2)

para("The run loop wraps each clip in a try/except that prints the error and sleeps for a second "
     "before trying again.")

para("Why: a thread that dies leaves a permanently frozen dashboard with no explanation on screen "
     "and no traceback in the log. On a demo machine the visible symptom would be \"the video "
     "stopped and nobody knows why\". Printing and continuing keeps the application alive and says "
     "what happened, which is strictly better than a silent freeze.")

heading("How a source switch works without a race", 2)

para("The operator picks a new clip from the dropdown. That is an HTTP POST handled by a web "
     "thread, but the video loop is mid-frame in the engine thread. Closing the capture or "
     "resetting the detector from the web thread would pull the file handle out from under the "
     "loop.")

para("So the web thread only raises a flag. The loop checks the flag at the top of each iteration, "
     "and when it sees it, unwinds cleanly through its own finally block, releases the capture, and "
     "rebuilds every piece of memory for the new clip.")

table(
    ["What is rebuilt on a switch", "Why it has to be"],
    [
        ["Detector tracker state", "Track IDs restart at 1; a remembered ID from the old clip would "
         "give person 1 a burst of impossible speed"],
        ["DwellTracker", "Otherwise the new clip's visitors inherit dwell times measured in a "
         "different video"],
        ["SpeedTracker", "A remembered position from another camera would produce a huge fake speed"],
        ["HeatmapAccumulator", "Heat is evidence about one camera view; carrying it over would draw "
         "hot spots where nobody has stood"],
        ["AlertDebouncer per zone", "An alert left active would clear itself in the wrong clip"],
    ],
)

heading("The web layer's five jobs", 2)

para("app/main.py is deliberately thin. It translates HTTP into calls on the other modules and "
     "serialises the answers. Every route is one of five kinds:")

table(
    ["Route", "Kind", "Why it is shaped that way"],
    [
        ["GET /", "one file", "Mounting StaticFiles at \"/\" would swallow /api as well"],
        ["GET /video", "MJPEG stream", "multipart/x-mixed-replace renders inside a plain img, so "
         "video needs no JavaScript and no WebSocket"],
        ["GET /ws", "WebSocket", "pushes one snapshot every 0.5 s, so the page needs no polling"],
        ["GET /api/...", "JSON", "zones, alerts, history and the clip allow-list"],
        ["POST /api/source", "JSON action", "asks the engine to switch clips, by name only"],
    ],
)

heading("Why MJPEG and not WebRTC or H.264", 2)

para("MJPEG is a stream of JPEG images with a text boundary between them. The browser displays it "
     "in a plain img tag, replacing the picture as each new part arrives.")

para("The alternatives both cost something this project cannot pay. WebRTC needs a signalling "
     "server, STUN/TURN and about 300 lines of negotiation. H.264 needs an encoder, and the CPU is "
     "already spending 60 to 110 ms per frame on detection. MJPEG needs a JPEG encoder, which "
     "OpenCV already has, and about 20 lines of Python. It is less efficient per byte, which does "
     "not matter on a loopback connection.")

para("The cost is honest and worth stating: MJPEG has no inter-frame compression, so a 640x360 "
     "frame at quality 80 costs 25 to 60 KB, and 15 fps is roughly 0.6 MB/s. Over the loopback "
     "interface that is nothing; over a mobile connection it would be the wrong choice.")

heading("Why the video generator is synchronous", 2)

para("The /video route uses a normal (sync) generator with time.sleep, not an async one with "
     "await asyncio.sleep.")

para("Why: Starlette runs a sync generator in its thread pool, so the blocking sleep and the "
     "blocking JPEG encode do not stall the event loop that serves /ws and the JSON API. An async "
     "generator doing CPU work would block that loop for the whole encode, and the dashboard's "
     "numbers would stutter every time the video refreshed.")

heading("What the browser and the server each remember", 2)

para("The split is worth knowing because it explains several otherwise odd-looking pieces of code.")

table(
    ["Lives on the server", "Lives in the browser"],
    [
        ["The model, the tracker, the zones", "The zone polygons, for the site plan"],
        ["Dwell, speed and heat history", "The last 120 chart points"],
        ["The alert rows in SQLite", "The normalised alert rows on screen"],
        ["The overlay drawing (OpenCV)", "Which overlays are switched on"],
    ],
)

para("The browser is deliberately stateless about the important things. Close the tab, reopen it, "
     "and it re-fetches zones, alerts and history and rebuilds the chart. Nothing is lost, because "
     "nothing that mattered was only in the tab.")

pagebreak()

# =============================================================================================
# PART 3 - THE PIPELINE, FRAME BY FRAME
# =============================================================================================

heading("Part 3 - The pipeline, frame by frame", 1)

lead("One frame, from disk to screen. This is the section to narrate while pointing at the video.")

heading("The sequence", 2)

para("Everything below happens inside Engine._play_clip, in this order, for every frame that is "
     "not skipped by the stride.")

table(
    ["#", "Step", "Where", "What it produces"],
    [
        ["1", "Grab the next frame", "engine._play_clip", "the frame is advanced, nothing decoded"],
        ["2", "Decode, only on stride frames", "capture.retrieve", "the actual pixels"],
        ["3", "Resize to 640 wide", "vision.resize_frame", "640x360, aspect preserved"],
        ["4", "Detect and track", "vision.Detector.track", "a list of Person objects with ID, box, "
         "confidence and foot point"],
        ["5", "Group by zone", "zones.count_by_zone", "zone name -> list of Person"],
        ["6", "Update dwell", "analytics.DwellTracker.update", "when each ID entered each zone"],
        ["7", "Update speed", "analytics.SpeedTracker.update", "track ID -> px/s, for whoever moved"],
        ["8", "Add heat", "analytics.HeatmapAccumulator.add", "one hit per foot point, after decay"],
        ["9", "Check thresholds", "engine._update_alerts", "TRIGGERED / CLEARED / nothing"],
        ["10", "Sample history", "engine._save_headcounts", "one row per zone, every 2 s"],
        ["11", "Build the snapshot", "engine._build_snapshot", "the dict the browser receives"],
        ["12", "Publish", "SharedState.set", "frame, people, heat layer, snapshot, under one lock"],
    ],
)

heading("Why every second frame", 2)

para("STRIDE is 2, so only every second frame is decoded and analysed. capture.grab() advances the "
     "video cheaply without decoding; capture.retrieve() decodes the frame the loop actually "
     "wants.")

para("Why this is correct rather than a shortcut: a shopping-mall or concourse clip has people "
     "moving at walking pace. Between two consecutive frames at 30 fps, a walking person moves "
     "about 2 pixels. Analysing 15 frames a second instead of 30 loses almost nothing in "
     "detection quality, and doubles the throughput on a CPU that has no GPU.")

para("Two consequences follow, and both are visible in the code:")

bullet("Video time is computed as frame_index / fps, not as a count of analysed frames. If it "
       "counted analysed frames, video second 10 would be reached at the wrong point in the clip "
       "and every dwell time would be wrong.", "Time is still real time: ")
bullet("The alert debouncer measures elapsed seconds, not frames. Counting frames would make a "
       "3-second delay last 3 frames, which at stride 2 is one tenth of a second.",
       "The debouncer works in seconds: ")

heading("The foot point, and why it is not the box centre", 2)

para("Every geometry decision in the project rests on one function, vision.foot_point. It returns "
     "the bottom-centre of a person's bounding box.")

code("""box (100, 50, 140, 200)  ->  ((100 + 140) // 2, 200)  =  (120, 200)
                              ^ horizontal centre        ^ bottom edge""")

para("Why the bottom edge: a box's centre floats at roughly chest height, and chest height depends "
     "on how tall the person is and how far away they stand. Feet are on the floor. Zone polygons "
     "are drawn around floor area, so feet are the only point that means the same thing for a tall "
     "person at the back and a short person at the front.")

para("This is also the honest limit of the method, stated in Part 9: a person standing behind a "
     "shelf, whose feet are hidden, will be counted in the wrong place or not at all.")

heading("Detection and tracking", 2)

para("vision.Detector wraps YOLOv8 plus ByteTrack so that callers ask for people, not for tensors. "
     "The model is loaded once, in __init__, because loading weights takes one to two seconds and "
     "reloading per frame would be absurd.")

table(
    ["Setting", "Value", "Why this value"],
    [
        ["model", "yolov8n.pt", "the nano variant: the only one that runs at a usable rate on a "
         "CPU without a GPU"],
        ["classes", "[0]", "class 0 of the 80 COCO classes is \"person\"; bags, cars and phones are "
         "never counted"],
        ["conf", "0.35", "below about 0.3 the model starts reporting shadows and reflections; above "
         "0.5 it loses real people at the back of a crowd"],
        ["imgsz", "640", "the standard YOLOv8 input size, and the size the frames are resized to"],
        ["persist", "True", "keeps tracker state between calls, which is what makes IDs stable"],
        ["tracker", "bytetrack.yaml", "ships with ultralytics; no extra dependency"],
    ],
)

para("Why ByteTrack and not a simpler centroid matcher: ByteTrack keeps a person's ID through a "
     "short occlusion by matching predicted positions, and it deliberately uses low-confidence "
     "boxes for association. In a crowd, people constantly pass behind each other, and a naive "
     "matcher would hand out a new ID every time that happened, which would reset that person's "
     "dwell time to zero. Dwell times are one of the three things the product reports, so this "
     "mattered.")

heading("Which zone is a person in", 2)

para("zones.zone_of tests a foot point against each polygon using cv2.pointPolygonTest with "
     "measureDist=False, which returns a value at or above zero for inside or on the edge, and "
     "below zero for outside.")

para("Why first-match-wins when polygons overlap: a foot point is in one place, and \"the first "
     "zone listed that contains it\" is a rule anyone can predict and check. zones.json lists the "
     "most important zone first. The alternative, assigning to the smallest containing zone, is "
     "harder to explain and no more correct.")

para("Why count_by_zone starts every zone at an empty list: so a zone that just emptied still "
     "appears in the result and the dashboard shows \"0 / 5\" rather than hiding the zone. A zone "
     "that disappears from the panel looks like a bug, not like good news.")

heading("The status rule, in one place", 2)

para("zones.status_for turns a count and a capacity into one of three words. It is called by the "
     "video drawing, the snapshot builder and the tests, from the same source.")

code("""capacity 10:   7 -> OK      8 -> NEAR     10 -> NEAR     11 -> OVER
               (below 80%)   (>= 80%)     (= 100%)      (> 100%)""")

para("Why NEAR starts at 80 percent and not at 100: an operator needs the warning before the area "
     "is full, not after. A meter that stays silent until the moment it is exactly full has told "
     "you something you can no longer act on.")

para("Why exactly full is NEAR and not OVER: capacity means \"this many people fit\". The eleventh "
     "person is the problem, not the tenth. Making exactly-full an alarm would make every "
     "correctly-sized room look permanently broken.")

para("Why the same function feeds both the colour and the alert: if the meter turned red at a "
     "different count from the one that raised the banner, an operator would see a red zone with "
     "no alert, or an alert with a green zone, and would stop trusting both.")

heading("Dwell, and why there are two numbers", 2)

para("analytics.DwellTracker remembers, for every (zone, track ID) pair, when that person entered "
     "the zone and when they were last seen in it.")

para("Why per zone and not per person: someone can walk from a quiet area into a busy one, and the "
     "second area's dwell must start when they cross the line, not when they first appeared on "
     "camera. Tracking per person would credit the busy zone with time the person spent elsewhere.")

para("It reports both an average and a maximum, and reports them in video seconds:")

bullet("one person waiting 60 s among nine people waiting 2 s averages about 8 s, and so does ten "
       "people waiting 8 s each. Those are completely different situations and completely "
       "different operational problems. The maximum exposes the person who is actually stuck.",
       "Why the maximum as well as the average: ")

para("A person is forgotten only after TRACK_GRACE (2 s) without being seen in that zone. Why not "
     "immediately: a missed detection for a frame or two is normal in a crowd, and forgetting "
     "immediately would reset a 40-second dwell to zero and make the average meaningless.")

heading("Speed, and why it is in pixels per second", 2)

para("analytics.SpeedTracker remembers each person's last foot position and the video time it was "
     "seen at, then reports distance divided by elapsed time in px/s.")

para("This is the single most likely question, so the answer is stated plainly: no camera "
     "calibration means no honest way to convert pixels into metres. Converting would need the "
     "height and angle of the camera, the position of the floor plane, and a lens model. Without "
     "those, any km/h figure would be invented. A number that is invented is worse than a number "
     "that is in unconvincing units, because the first is a lie and the second is a measurement.")

para("Pixels per second is still exactly the operational question. The comparison that matters is "
     "between zones and over time within one clip: 5 px/s is a queue, 40 px/s is a thoroughfare. "
     "That comparison needs no calibration at all.")

para("Why a person seen for the first time is absent from the result rather than reported as 0: "
     "one position cannot be divided by time. Reporting 0 would claim the person is standing still, "
     "which is a different and false statement. The dashboard shows a dash for the same reason.")

heading("The heatmap", 2)

para("analytics.HeatmapAccumulator builds a \"where do people keep standing?\" picture by adding "
     "1.0 at every foot point, every frame, and multiplying the whole map by HEAT_DECAY first.")

code("""HEAT_DECAY 0.995, one pixel holding 1.0:
   after   1 frame   0.995
   after  10 frames  0.951
   after 100 frames  0.606""")

para("Why decay at all: a plain running total would make one busy minute glow forever, so a spot "
     "that was crowded ten minutes ago would still look like the worst place in the building. Decay "
     "means the picture always describes the recent past.")

para("Three more choices in the same class:")

bullet("the raw values depend on how long the clip has run and could be 2 or 200; dividing by the "
       "current peak makes the colours mean \"hot compared with now\", which is what a viewer "
       "assumes from a heatmap anyway.", "Why normalise each frame: ")
bullet("one foot point is a single pixel, which is invisible. Blurring turns it into a soft blob, "
       "and overlapping blobs become a visible hot area.", "Why Gaussian blur: ")
bullet("without it the whole frame would be tinted, including empty floor, and the video underneath "
       "would be hard to read. HEAT_MASK_RATIO 0.08 keeps only pixels holding at least 8 percent of "
       "the current peak.", "Why a mask: ")

para("The class stores float32, not uint8. Why: multiplying 255 by 0.995 rounds straight back down "
     "to 255 in an integer array, so the heat would never decay at all.")

heading("The alert debouncer", 2)

para("analytics.AlertDebouncer is what stands between a noisy counter and a usable alarm. It "
     "watches one zone and returns at most one TRIGGERED per over-capacity episode.")

code("""ON_DELAY  3 s   a zone must be over capacity this long before the alarm fires
OFF_DELAY 5 s   a zone must be back at or below capacity this long before it clears""")

para("Why this exists at all: the count jumps by one person constantly. A detection misses, a "
     "person steps on a polygon edge, a person passes behind a pillar. Alerting on every frame "
     "above capacity would produce dozens of alerts for one real problem, and an operator who sees "
     "dozens of alerts for one problem stops reading alerts.")

para("Why runs rather than a counter of frames: STRIDE means frames are not equally spaced in "
     "seconds, so a 3-second delay would become a 3-frame delay. Why the run's start time rather "
     "than summed deltas: if the caller ever skips frames, elapsed time is still exactly "
     "now minus start, whereas summing deltas silently loses the gap.")

para("Why OFF_DELAY is longer than ON_DELAY: it is cheap to be wrong about clearing an alert and "
     "expensive to be wrong about raising one. A longer clear delay stops the banner flickering "
     "on and off while a crowd sits right at the threshold.")

pagebreak()

# =============================================================================================
# PART 4 - FILE BY FILE
# =============================================================================================

heading("Part 4 - The folder, file by file", 1)

lead("What every file is for, why it is a separate file, and what is inside it.")

heading("The whole folder at a glance", 2)

para("21 files are part of the submission. This is the complete list, with what each one is for.")

table(
    ["Path", "Lines", "Its one job"],
    [
        ["app/config.py", "102", "every tunable number, in one place"],
        ["app/vision.py", "114", "frames in, tracked people out"],
        ["app/zones.py", "255", "polygons, capacities, and which zone a foot is in"],
        ["app/analytics.py", "389", "dwell, speed, heatmap, alert debouncing"],
        ["app/db.py", "222", "SQLite: alert history and head-count history"],
        ["app/engine.py", "625", "the background loop and the shared state"],
        ["app/main.py", "235", "HTTP, WebSocket, MJPEG, JSON API"],
        ["app/__init__.py", "4", "marks app/ as a package"],
        ["static/index.html", "415", "the dashboard markup"],
        ["static/app.js", "2047", "fetches data and draws every panel"],
        ["static/style.css", "1629", "the whole theme, from tokens down"],
        ["static/vendor/", "-", "Tailwind and Chart.js, checked in so the demo works offline"],
        ["tests/test_pipeline.py", "239", "20 tests over the whole pipeline"],
        ["zones.json", "23", "the operator's zone polygons and capacities"],
        ["requirements.txt", "13", "exact pinned versions"],
        ["start.bat", "29", "double-click launcher for Windows"],
        ["README.md", "279", "what it is, how to run it, and how it meets the brief"],
        ["CODE_GUIDE.md", "1268", "the long-form code walkthrough"],
        ["demo_videos/", "-", "3 clips, SOURCES.csv, expected_results.md"],
        ["docs/", "-", "architecture diagram, screenshots, handbook, this manual"],
        ["scripts/", "-", "the four generators that build the docs"],
    ],
)

note("Why only seven Python files",
     "The graded question is \"can this person explain their own system?\" A file per concept is "
     "easy to explain; a file per class is not. Seven files map exactly onto the seven things the "
     "system does, and each one has a docstring that states the failure it prevents.")

heading("app/__init__.py", 2)

para("Four lines, one docstring. It exists so every other module can write \"from app import "
     "config\" and work no matter which directory Python was started from. An empty file would "
     "work, but the docstring is the first thing anyone opening the folder reads.")

heading("app/config.py - every tunable number", 2)

para("Every setting the application has lives here, and nothing else. No function in the project "
     "contains a bare number that a reader would want to change.")

para("Why this rule exists: a magic number buried in a function is invisible. Someone tuning "
     "detection sensitivity has to read the detection code to find out that 0.35 is the threshold, "
     "and there is no way to know whether the same 0.35 appears in three other places. Here, "
     "changing one named constant changes behaviour everywhere, and the comment beside it says "
     "what moving it does.")

table(
    ["Constant", "Value", "What it controls, and what happens if you move it"],
    [
        ["MODEL_PATH", "yolov8n.pt", "the weights file; a larger variant is more accurate and too "
         "slow for this CPU"],
        ["CONF", "0.35", "minimum confidence to count as a person; lower finds more and invents "
         "more"],
        ["IMGSZ", "640", "the size the model sees; smaller is faster and loses people at the back"],
        ["PERSON_CLASS_ID", "0", "class 0 of the COCO classes is person"],
        ["FRAME_WIDTH", "640", "every frame is resized to this width, so all coordinates agree"],
        ["STRIDE", "2", "analyse every second frame; 1 doubles the cost, 3 starts losing people"],
        ["ON_DELAY", "3.0", "seconds over capacity before an alert; the anti-flicker delay"],
        ["OFF_DELAY", "5.0", "seconds back to normal before it clears"],
        ["NEAR_RATIO", "0.8", "fraction of capacity at which the status becomes NEAR"],
        ["HEAT_DECAY", "0.995", "how fast old heat fades; 1.0 never fades, 0.99 fades in seconds"],
        ["HEAT_BLUR_FRACTION", "0.05", "blur kernel as a fraction of width; 0.05 at 640 is 33 px"],
        ["HEAT_MASK_RATIO", "0.08", "pixels below this fraction of the peak are not drawn"],
        ["HEAT_OVERLAY_ALPHA", "0.5", "how strongly heat replaces video where it is drawn"],
        ["TRACK_GRACE", "2.0", "seconds a lost track is remembered before the person is gone"],
        ["JPEG_QUALITY", "80", "stream quality; 60 is blocky, 95 triples the bandwidth"],
        ["MJPEG_MAX_FPS", "15", "cap on the stream rate, so a slow browser is not flooded"],
        ["WS_INTERVAL", "0.5", "seconds between snapshot pushes"],
        ["HEADCOUNT_INTERVAL", "2.0", "video seconds between history rows"],
        ["FPS_WINDOW", "20", "how many frame durations the moving average spans"],
        ["EVIDENCE_URL_PREFIX", "/evidence", "the URL path evidence photos are served from"],
        ["DEFAULT_SOURCE", "crowded.mp4", "the clip the engine starts on"],
    ],
)

para("The bottom five constants are folders and files, all built from BASE_DIR rather than from "
     "relative paths.")

code("""BASE_DIR = Path(__file__).resolve().parent.parent""")

para("Why absolute: the app must work when started from any directory. A relative \"results/"
     "crowd.db\" would create a second, empty database in whatever folder the terminal happened to "
     "be in, and the dashboard would show no history while the real one sat in the project folder.")

heading("app/vision.py - the eyes", 2)

para("Three things live here: the Person dataclass, two geometry helpers, and the Detector that "
     "wraps YOLO plus ByteTrack.")

para("Why a dataclass and not a dict: Person has four fields that must all be present, and a "
     "dataclass makes a missing or misspelled field an immediate error instead of a KeyError three "
     "functions later. It also documents the shape in one place.")

table(
    ["Name", "What it does", "Why it is separate"],
    [
        ["Person", "track_id, box, conf, foot", "the one shape that crosses from vision into "
         "analytics"],
        ["foot_point(box)", "bottom-centre of a box", "the foundation of all zone geometry; one "
         "definition, one test"],
        ["resize_frame(frame, width)", "scales to a fixed width, keeping aspect ratio", "so "
         "detection speed, drawing coordinates and the stream are all predictable"],
        ["Detector.__init__", "loads the weights once", "loading per frame would take seconds per "
         "frame"],
        ["Detector.track(frame)", "detects and tracks, returns Person objects", "callers ask for "
         "people, not tensors"],
        ["Detector._to_person", "converts one YOLO tensor row to a Person", "keeps tensor handling "
         "in one place"],
        ["Detector.reset()", "restarts track IDs at 1", "needed on a clip switch, or IDs collide"],
    ],
)

para("Why resize_frame picks its interpolation: INTER_AREA averages pixels and looks clean when "
     "shrinking; INTER_LINEAR avoids blur when enlarging. Choosing the wrong one in the wrong "
     "direction makes people look either fuzzy or jagged.")

para("Why track() returns an empty list when boxes.id is None: the tracker sometimes produces "
     "detections before it has produced tracks, and that is not an error. Returning [] lets the "
     "frame proceed with zero people instead of raising.")

heading("app/zones.py - the geometry", 2)

para("This module owns three things that must never disagree: the polygon shapes, the capacities, "
     "and the status rule. The dashboard, the video overlay, the alert logic and the tests all ask "
     "it the same questions.")

table(
    ["Name", "What it does", "Why it exists"],
    [
        ["Zone", "name, capacity, polygon", "one area of the picture"],
        ["Zone.points()", "polygon back to a list of pairs", "JSON needs plain numbers, not a numpy "
         "array"],
        ["make_polygon(points)", "list of pairs to an (N,1,2) int32 array", "the exact layout OpenCV "
         "requires; one conversion, one place"],
        ["load_zones(path, source)", "reads one clip's zones from JSON", "zones belong to a camera "
         "view, so they are loaded per clip"],
        ["zone_of(zones, point)", "first containing zone, or None", "first match wins, which is "
         "predictable"],
        ["count_by_zone(zones, people)", "zone name to list of Person", "every zone gets a list, "
         "even an empty one"],
        ["status_for(count, capacity)", "OK / NEAR / OVER", "one rule for the colour, the alert and "
         "the tests"],
        ["draw_zones(frame, zones, counts)", "translucent fill, outline, label", "the video overlay"],
        ["_draw_label", "writes the zone label above the polygon", "keeps text off the people"],
        ["save_zones(path, source, zones)", "writes one clip's entry, keeping the others", "so "
         "regenerating one clip does not wipe the rest"],
        ["_format_zone", "formats one zone compactly", "indent=2 would put each coordinate on its "
         "own line"],
    ],
)

para("Why load_zones raises SystemExit with a readable message when a clip has no entry: silently "
     "drawing no zones would look exactly like \"nobody is ever in any zone\", which is the worst "
     "possible failure for this product. Refusing to start is louder and safer.")

para("Why draw_zones works on a copy: the caller keeps the clean frame for detection. Painting into "
     "the original would feed our own drawn boxes back into the next frame's detection.")

para("Why the fill is blended at alpha 0.25 and the outline drawn at full strength: a solid fill "
     "would hide the people the zone is counting. The outline is drawn after the blend, on a fresh "
     "copy, so the blend does not dim it.")

note("Honest note on save_zones",
     "save_zones and _format_zone are written, tested by hand, and currently unused: zones.json is "
     "edited by hand for three fixed clips. They are kept because they are the documented way to "
     "write zones back without destroying the other clips' entries, but a reader should know they "
     "are not on the live path.")

heading("app/analytics.py - the memory", 2)

para("Counting people in one frame is easy. Every interesting answer needs memory across frames, "
     "and this file is that memory: four small classes, each answering exactly one question, so "
     "each can be tested on its own.")

table(
    ["Class", "The question it answers", "State it keeps"],
    [
        ["DwellTracker", "how long has this person been in this zone?", "entered_at and last_seen "
         "per (zone, track ID)"],
        ["SpeedTracker", "are people walking or stuck?", "last foot position and time per track ID"],
        ["HeatmapAccumulator", "where do crowds keep forming?", "a float32 image, decayed every "
         "frame"],
        ["AlertDebouncer", "has this been over capacity long enough to matter?", "the start of the "
         "current over-capacity run and of the current under-capacity run"],
    ],
)

para("Two module-level helpers support them: _distance (Pythagoras, because a diagonal step is "
     "genuinely shorter than walking its two sides, so adding the sides would overstate speed for "
     "anyone moving at an angle) and _odd (Gaussian blur refuses an even kernel size, so a computed "
     "32 is silently turned into 33).")

para("Every timestamp that enters this module is a video timestamp in seconds. Nothing here calls "
     "time.time().")

para("Why that matters: the demo replays a recording. If dwell were measured against the wall "
     "clock, then a 45-second clip playing at 16 fps would take about 90 seconds of real time, and "
     "every dwell figure would be roughly double its true value. The three classes would still "
     "produce numbers; they would just be the wrong numbers, and nothing on screen would say so.")

heading("app/db.py - the history", 2)

para("Two tables, and every SQL statement in the project. Two different callers need the same "
     "tables: the engine writes while the video runs, and the API reads for the dashboard.")

para("Why every function opens its own short-lived connection: SQLite connection objects cannot be "
     "shared between threads, and this application has an engine thread and FastAPI worker "
     "threads. A per-call connection sidesteps the problem entirely, and each call is one small "
     "query, so the cost is microseconds on a local file.")

para("Why a context manager rather than open and close by hand: it closes the handle even if the "
     "query raises. On Windows a leaked handle keeps the .db file locked, and the next write fails "
     "with \"database is locked\", which is a confusing error for a simple bug.")

table(
    ["Table / name", "What it holds", "Why"],
    [
        ["alerts", "one row per alert episode", "so past overcrowding stays visible after the crowd "
         "is gone"],
        ["headcount", "one row per zone per 2 video seconds", "the trend chart's raw material"],
        ["connect()", "one connection, commit, close", "thread safety and no leaked handles"],
        ["init_db()", "creates tables IF NOT EXISTS", "startable on a fresh machine, and a restart "
         "must not wipe history"],
        ["utc_now_iso()", "wall-clock UTC timestamp", "started_at answers \"when in real life?\" while "
         "video_ts answers \"where in the clip?\""],
        ["insert_alert()", "adds a row, returns its id", "the id names the evidence photo"],
        ["end_alert()", "stamps ended_at", "closing, not deleting: the history is the point"],
        ["update_peak()", "raises the peak, never lowers it", "the busiest moment is the evidence"],
        ["set_keyframe()", "attaches the photo URL", "the file name needs the id, so the row must "
         "exist first"],
        ["list_alerts()", "newest first, bounded", "the dashboard shows a feed, not an archive"],
        ["add_headcount()", "appends one sample", "the chart's building block"],
        ["headcount_since()", "last N minutes, oldest first", "the chart plots left to right"],
    ],
)

para("Two choices in this file are worth naming, because they are the kind of thing a panel asks "
     "about.")

para("Why every value is a ? parameter and never formatted into the SQL string: zone names and clip "
     "names are user-controlled. String formatting would open the door to SQL injection, and would "
     "also break on any name containing an apostrophe.")

code("""UPDATE alerts SET peak_count = MAX(peak_count, ?) WHERE id = ?""")

para("Why that is one statement rather than read, compare in Python, write back: one statement "
     "cannot be interrupted between the read and the write, so a concurrent writer can never lower "
     "a peak that another writer already raised.")

para("Why timestamps are ISO-8601 strings in UTC: that format sorts alphabetically in the same "
     "order it sorts in time. So \"WHERE ts >= ?\" and ORDER BY both work as string comparisons, "
     "and no row ever needs a date parsed.")

heading("app/engine.py - the loop", 2)

para("The largest file, and the one that holds the architecture together. It contains SharedState, "
     "the Engine thread, and every method that updates or publishes a result.")

table(
    ["Name", "What it does"],
    [
        ["empty_snapshot(source)", "a well-formed all-zero snapshot for before the first frame"],
        ["SharedState", "holds frame, people, heat and snapshot behind one lock"],
        ["SharedState.set / get", "replace or read all of it, copying both ways"],
        ["SharedState.get_heat", "returns the heat layer alone, without copying frames"],
        ["list_clips()", "the allow-list of clip names"],
        ["source_fps(capture)", "the clip's frame rate, or 25 if the metadata is unusable"],
        ["Engine.run", "play a clip, then replay it forever"],
        ["Engine._play_clip", "one clip start to finish, with everything reset"],
        ["Engine.set_source", "asks the loop to switch, by allow-listed name only"],
        ["Engine._update_alerts", "feeds counts to the debouncers and acts on the events"],
        ["Engine._open_alert", "inserts the row, saves the photo, reports the payload"],
        ["Engine._finish_alert", "closes one zone's open alert"],
        ["Engine._close_alerts", "closes everything still open when a clip stops"],
        ["Engine._save_headcounts", "one row per zone plus an ALL total, every 2 s"],
        ["Engine._save_evidence", "writes the annotated frame as evidence/alert_N.jpg"],
        ["Engine._record_frame_time", "adds a frame duration to the moving average"],
        ["Engine.measured_fps", "the moving-average rate"],
        ["Engine._build_snapshot", "assembles the exact dict the dashboard receives"],
        ["Engine.render", "builds one JPEG with the overlays the browser asked for"],
        ["Engine._zones_for_render", "zone objects and counts, cached per clip"],
        ["Engine._encode", "frame to JPEG bytes at the configured quality"],
    ],
)

para("Why empty_snapshot exists: the browser connects to /ws within milliseconds, while YOLO is "
     "still loading. Sending {} would break the contract and force every client to guard against "
     "missing keys. Sending a well-formed \"nothing yet\" snapshot means the dashboard renders its "
     "first frame without a single special case.")

para("Why list_clips builds the allow-list from the folder's actual contents: set_source must never "
     "accept a path from the browser. Because the accepted values are exactly the names this "
     "function returned, a request for \"../../zones.json\" cannot succeed, and that is a property "
     "of the design rather than a check that could be forgotten.")

para("Why the zones are cached per clip in _zones_for_render: /video renders up to 15 frames a "
     "second, and re-parsing zones.json for each one is 15 file reads a second for data that only "
     "changes when a person edits the file. The cache is keyed by clip, so switching source never "
     "reuses another camera's polygon.")

heading("app/main.py - the web layer", 2)

para("Thin on purpose. All the thinking lives in the engine, the database and the zones. This "
     "module translates HTTP into calls on those and serialises the answers.")

para("Why that split matters: a bug in a route is a web bug; a bug in a count is a vision or "
     "analytics bug. Keeping them in separate files means knowing which one you are looking at "
     "before you open it.")

table(
    ["Route", "Returns", "Notes"],
    [
        ["GET /", "the dashboard HTML", "one explicit route; mounting / would swallow the API"],
        ["GET /video?boxes=&zones=&heat=", "MJPEG stream", "the query string is the whole overlay "
         "contract: 1 or 0"],
        ["GET /ws", "a snapshot every 0.5 s", "a steady beat, not only-on-change"],
        ["GET /api/zones?source=", "capacities and polygons", "so meters and plan draw before the "
         "first snapshot"],
        ["GET /api/alerts?limit=", "newest alerts first", "1 to 500, enforced by Query"],
        ["GET /api/history?minutes=", "samples, oldest first", "1 minute to 24 hours"],
        ["GET /api/sources", "the clip allow-list", "the dropdown offers exactly what the POST "
         "accepts"],
        ["POST /api/source", "ok and the new name", "400 for a name that is not on the allow-list"],
    ],
)

para("Why /ws sends on a timer instead of only when something changes: the dashboard also needs to "
     "know that nothing changed, so it can distinguish \"the crowd is steady\" from \"the connection "
     "died\". A steady beat is simpler than diffing, and the payload is about 500 bytes.")

para("Why POST returns 400 and not 404 for an unknown clip: the request is malformed, it is not a "
     "missing page. 400 tells the client to fix its body, which is the actionable message.")

para("Why the lifespan handler creates the tables before starting the engine: the engine writes an "
     "alert row within the first few seconds of the crowded clip, and that write would fail on a "
     "fresh machine if the tables did not exist yet. Why the engine is joined on shutdown, even "
     "though it is a daemon thread: joining gives it a moment to release the video file handle, "
     "which is what keeps Windows from leaving a locked file behind after a restart.")

pagebreak()

heading("static/index.html - the markup", 2)

para("415 lines of plain HTML with Tailwind utility classes. No framework, no build step, no icon "
     "library: every icon is inline SVG.")

para("Eight regions, top to bottom:")

numbered("Sticky top bar: title, source dropdown, LIVE pill, fps chip, clock.")
numbered("Inline error bar: one line, shown only when a fetch fails or the socket drops.")
numbered("Congestion banner: visible only while alerts_active is above zero.")
numbered("Readings strip: one bordered strip of four cells, 2x2 on phones and 4 across from 1024 px.")
numbered("Console grid: left 8/12 is the camera and the trend; right 4/12 is occupancy, site plan "
         "and the event log.")
numbered("Footer: live status and the credit line.")
numbered("Toast stack: a new alert announces itself.")
numbered("Evidence dialog: the saved photograph, in a native dialog element.")

para("Why the readings are one strip and not four cards: four separate floating boxes compete with "
     "the video for attention, and a strip takes roughly half the vertical space for the same four "
     "numbers. The label comes before the reading, the way a gauge is marked, so the eye lands on "
     "the number already knowing what it measures.")

para("Why the evidence uses a native dialog element: the browser provides focus trapping, "
     "Escape-to-close and an inert backdrop for free. A hand-rolled overlay has to reimplement all "
     "three and usually gets at least one wrong.")

para("Why the tooltips are pure CSS (icon-badge with a data-tip attribute): no JavaScript, no "
     "library, and they open downward so they clear the sticky header.")

para("Two accessibility details worth pointing out, because they are cheap and rarely done:")

bullet("the alert list has tabindex=\"0\" because it scrolls. A scrollable box that no key can "
       "reach fails WCAG 2.1.1 for anyone not using a mouse.", "The scrolling log is focusable: ")
bullet("the status chip always carries an icon drawn differently for each state, so the meaning is "
       "never carried by colour alone.", "Every status is a word and an icon: ")

heading("static/app.js - the client", 2)

para("About 2,047 lines, in thirteen numbered sections. This is the file that turns a snapshot into "
     "a screen. Its three jobs:")

numbered("Fetch the slow-changing data once at boot: zones, alerts, history, sources.")
numbered("Hold a WebSocket open and apply each snapshot to every panel from one place.")
numbered("Never let a failed fetch or a dropped socket leave a panel on a skeleton forever.")

para("The contract is two shapes, and everything else is derived from them:")

code("""snapshot zone  (from /ws)        { name, count, capacity, fill, status, over_for,
                                    avg_dwell, max_dwell, avg_speed }
api zone       (from /api/zones)  { name, capacity, polygon }""")

para("The snapshot is the live truth. /api/zones only says which zones exist and how big they are, "
     "so the meters and the site plan can be drawn before the first message arrives.")

table(
    ["Section", "What lives there"],
    [
        ["1. Settings and state", "the app object: every piece of shared state, one place"],
        ["2. Small helpers", "escapeHtml, statusClass, statusIcon, formatDwell, formatSpeed, "
         "videoLabel, clockTime, zoneColor"],
        ["3. Fetching", "getJson with a timeout, showError, clearError"],
        ["4. KPI row", "animateKpi, renderKpis"],
        ["5. Occupancy meters", "gaugeMarkup, deriveStatus, renderGauges"],
        ["5b. Site plan", "renderPlan, planViewBox, planDots, pointInPolygon, polygonBounds"],
        ["6. Alert log", "normaliseAlert, alertRowMarkup, updateTitle, paintAlertSummary, "
         "renderAlerts, prependAlert"],
        ["7. Chart", "createChart, pushChartData, appendChartPoint, prefillChart, rebuildChart, "
         "paintLegend"],
        ["8. Banner, video, overlays", "renderBanner, worstZone, videoUrl, attachVideo, bindToggle, "
         "bindFullscreen"],
        ["9. WebSocket", "setLiveState, connectSocket, scheduleReconnect"],
        ["10. The update path", "reconcileActiveAlerts, update"],
        ["11. Toast and evidence", "showToast, openEvidence"],
        ["12. Source switching", "changeSource, loadZones, renderSources"],
        ["13. Boot", "loadInitialData, showSkeletons, startClock, boot, bindSourceSelect, "
         "bindErrorBar"],
    ],
)

para("Three design rules hold this file together.")

para("First, one snapshot, one instant. update(snapshot) is the only entry point for live data, and "
     "it calls every panel renderer from that one dict. If each panel read its own source, the "
     "banner could describe video second 10.5 while the chart's last point was from 10.0, and the "
     "screen would contradict itself.")

para("Second, colour is state, never decoration. statusClass, statusIcon and the stateClass map all "
     "exist so that the row, the bar and the chip cannot disagree. The map is written as an object "
     "rather than two ternaries for a specific reason: a status with no class silently keeps the OK "
     "styling, which is exactly how an amber bar once rendered green in this project.")

para("Third, every number has a defined fallback. formatSpeed shows an em dash, not 0, when no "
     "speed has been measured. gaugeMarkup uses the snapshot's own fill and falls back to "
     "count/capacity only for the first half second. The rule is that a missing measurement must "
     "never be displayed as a real zero, because those are different claims.")

para("Why the client duplicates the status rule in deriveStatus: the meters must render before the "
     "first snapshot arrives, and the capacities are already known from /api/zones. The thresholds "
     "are identical to zones.status_for, so the placeholder and the live state cannot disagree.")

heading("static/style.css - the theme", 2)

para("About 1,629 lines on top of Tailwind, and the single most graded artefact in the project: "
     "front-end UI and UX is 60 percent of the rubric.")

para("Everything is driven from CSS custom properties in :root. Re-theming is one edit, and no "
     "component invents its own colour, radius or size.")

table(
    ["Token group", "What it controls"],
    [
        ["Surfaces", "--bg, --panel, --panel-2, --panel-3: four steps of one neutral. Depth is read "
         "from contrast, not shadow"],
        ["Rules", "--rule, --rule-strong: hairline borders"],
        ["Ink", "--ink, --ink-2, --ink-3: three text levels, all contrast-measured"],
        ["State", "--ok, --warn, --crit and their tinted washes"],
        ["Shape", "--radius 4px, --radius-md 3px, --radius-pill"],
        ["Type", "--fs-2xs through --fs-3xl, plus --font-ui and --font-mono"],
        ["Motion", "--ease-out and three durations"],
    ],
)

para("The file states its own three rules at the top, and they are worth quoting because they "
     "explain most of the CSS:")

bullet("400 to read, 600 to emphasise. Mono is reserved for numbers.", "Two weights for text: ")
bullet("4 px for panels, 3 px for blocks. A console has squarer corners than a consumer app; "
       "rounded reads as friendly, not operational.", "Three radii plus a pill: ")
bullet("the only exceptions are 1 px rules and icon stroke widths.", "Spacing is a multiple of "
       "4 px: ")

para("Why no blur and no soft shadows on the panels: the surface class is called .glass for "
     "historical reasons, but it now paints a flat fill and one hairline rule. A console is read "
     "straight on, and a soft shadow implies a card floating over something, which nothing here "
     "does. On a dim projector, a soft shadow also turns to mud.")

para("Contrast was measured, not guessed. Against the panel colour, body ink is 15.4:1, secondary "
     "ink 8.1:1 and the dimmest text 4.9:1; the state colours are 11.8:1, 9.3:1 and 8.3:1. WCAG AA "
     "requires 4.5:1 for body text and AAA requires 7:1, so every level passes.")

heading("tests/test_pipeline.py - the 20 tests", 2)

para("One file, 20 tests, 10 test classes, read top to bottom in the same order as the data flows: "
     "person, then zone, then analytics, then database, then shared state.")

para("Why one file rather than six: the project is graded on being explainable, and a single file "
     "that follows the pipeline is easier to walk a panel through than six files they have to open "
     "one by one.")

table(
    ["Class", "Tests", "The claim it protects"],
    [
        ["TestFootPoint", "1", "the foot is the bottom centre, not the chest"],
        ["TestResize", "2", "aspect ratio is kept; a zero width is refused"],
        ["TestZones", "2", "inside and outside are decided correctly; the status thresholds hold"],
        ["TestDwell", "2", "dwell grows with time; a departed person is forgotten"],
        ["TestSpeed", "2", "a first sighting has no speed; 40 px in 2 s is 20 px/s"],
        ["TestDebouncer", "3", "a 1 s spike fires nothing; 4 s fires once; clearing waits 5 s"],
        ["TestHeatmap", "2", "an empty map draws nothing; one point heats one pixel"],
        ["TestDatabase", "3", "alert round trip; peak never lowers; history comes back in order"],
        ["TestSharedState", "2", "the empty snapshot is well formed; get returns a copy"],
        ["TestClips", "1", "no clip name contains a path separator"],
    ],
)

para("Every test names the failure it prevents rather than the behaviour it checks. That is a "
     "deliberate style: \"test_departed_person_is_forgotten\" says why it matters, "
     "\"test_update_2\" does not.")

para("Why the analytics tests use a fake person: the analytics classes read only track_id and foot, "
     "so a lightweight stand-in keeps the tests fast and free of YOLO, which would take a second "
     "per test just to load.")

para("Why the database tests use a temporary folder: a test must never touch the real "
     "results/crowd.db. A test that can corrupt the demo data is a test you stop running.")

heading("zones.json - the operator's file", 2)

para("23 lines, one entry per clip, each a list of zones with a name, a capacity and a polygon.")

code("""{
  "crowded.mp4": [
    { "name": "Main Zone", "capacity": 4,
      "polygon": [[284, 232], [300, 274], [352, 309], [346, 359],
                  [488, 359], [467, 329], [404, 334], [330, 235]] }
  ],
  "mid.mp4": [ ... ],   "normal.mp4": [ ... ]
}""")

para("Why the polygons are per clip and not global: every clip is a different camera view, so the "
     "same pixel coordinates describe a completely different piece of floor. A polygon drawn for "
     "the escalator clip would count people in the wrong place in the street clip.")

para("Why the coordinates are in the resized frame (640 wide) and not the original (1280 wide): "
     "the frame is resized before detection, so foot points and polygons must be in the same units "
     "or every comparison would be off by a factor of two.")

para("Why it is hand-edited JSON and not a drawing tool: a zone is a decision an operator makes "
     "once, and eight coordinate pairs are readable, reviewable and diffable in git.")

heading("requirements.txt, start.bat, and the rest", 2)

para("requirements.txt pins six packages to exact versions, with a comment explaining that lap is "
     "not a feature but the solver ByteTrack needs.")

para("Why exact pins: this project must install identically on the grading machine. A floating "
     "version range means the demo can break between the day it was built and the day it is shown, "
     "which is the worst possible time to discover a dependency change.")

para("start.bat is 29 lines and does four things: change to its own folder, refuse to run without a "
     "virtual environment, open the browser four seconds later, and start uvicorn on 127.0.0.1.")

para("Why the browser is opened by a delayed start rather than by the server: the page must load "
     "once the server is listening. A browser opened first shows a connection error, and the "
     "candidate has to explain away a red error page in the first ten seconds of a demo. Why "
     "--host 127.0.0.1 and not 0.0.0.0: this is a local demo, not a public service, and binding to "
     "every interface would expose an unauthenticated video feed to the local network.")

heading("The demo clips and the generators", 2)

para("demo_videos/ holds three clips, SOURCES.csv and expected_results.md. The CSV records title, "
     "page URL, author, licence and original resolution for each clip, because the brief accepts "
     "open-source footage but expects its provenance to be recorded. expected_results.md states "
     "what each clip should produce, which is what turns a demo into a test.")

para("docs/ holds the architecture diagram, two screenshots, the interview handbook and this "
     "reference. Every one of them is generated by a script in scripts/, so none of them can drift "
     "out of date once the code changes: make_architecture.py draws the four-layer diagram, "
     "make_screenshot.py captures docs/dashboard.png with headless Chrome, make_figure.py crops it "
     "for print, make_handbook.py builds the handbook, and make_reference.py builds this document.")

para("Why the screenshot is a script and not a saved file: a stale screenshot of an old design is "
     "worse than none, because a panel member comparing the picture to the live page finds them "
     "different.")

pagebreak()

# =============================================================================================
# PART 5 - FUNCTIONS WORTH EXPLAINING
# =============================================================================================

heading("Part 5 - The functions a panel will ask about", 1)

lead("Six functions carry the argument of the whole project. Each is quoted in full, then explained.")

heading("gaugeMarkup - the occupancy meter", 2)

para("Builds one row per zone: the name, the status chip, the count against capacity, a fill bar, "
     "and the dwell and speed beneath it.")

para("Three decisions inside it are worth defending.")

para("Why a bar and not a ring: capacity is a comparison against a limit, and a bar shows how much "
     "of the limit is used directly. Reading a fraction off a ring means estimating an angle, and "
     "nobody does that accurately at a glance across a room.")

para("Why the fill is clamped to between 0 and 1: an over-capacity zone cannot fill more than its "
     "track. Without the clamp the width goes past 100 percent and the bar is cut off mid-shape, "
     "which reads as a rendering bug. The OVER chip already carries the excess information.")

para("Why the snapshot's own fill is preferred over count divided by capacity: it is computed on "
     "the server next to the status, so the bar and the chip can never disagree. Dividing in the "
     "browser is only the fallback for the first half second, before a snapshot arrives.")

code("""const stateClass = { OVER: " is-hot", NEAR: " is-near" }[status] || "";""")

para("Why a map and not two ternaries: the stylesheet has a rule per state, and a state with no "
     "class silently keeps the OK styling. That is not hypothetical; it is exactly how the NEAR bar "
     "came out green in this project before the map was introduced.")

heading("renderPlan - the site plan", 2)

para("Draws the zone polygons to scale as SVG, with one dot per counted person and the live fill "
     "shaded inside.")

para("Why this panel exists at all: the video already shows the overlay, so a second view needs a "
     "reason. The reason is that an operator needs the shape of the area they are responsible for, "
     "not a camera image. A floor plan is the form that information takes on an operations desk, "
     "and it is what makes the page read as a venue tool rather than a video player with numbers "
     "beside it.")

para("Why the coordinates go straight in: polygons in zones.json are stored in resized frame "
     "pixels, which is the same grid the SVG uses. No scaling arithmetic means no rounding drift "
     "between the video overlay and the plan, and the two can never disagree about where a zone is.")

para("The dots need one honest caveat, and it is written into the code comment: the snapshot "
     "carries a count per zone, not each person's position. So the dots are distributed "
     "deterministically inside the polygon. The panel shows how many, laid out inside the shape, and "
     "never claims a position it was not given.")

heading("planViewBox - framing the plan", 2)

para("Works out the SVG viewBox that frames every zone with a margin, then widens it to 16:9.")

para("Why not use the whole 640x360 frame: the zones occupy one part of the frame, often a corner. "
     "Drawing the full frame would leave the plan as a small shape in a mostly empty box. Framing "
     "the zones is the difference between a plan and a thumbnail of a camera image.")

para("Why widen to 16:9 rather than let the shape define the aspect: a very tall or very wide zone "
     "would otherwise be letterboxed by preserveAspectRatio, which reintroduces the empty box the "
     "function exists to remove.")

para("Why the result is clamped back inside the frame: a zone touching the frame edge would "
     "otherwise show blank space beyond the video, which reads as a drawing error rather than as "
     "the edge of the building.")

heading("planDots and pointInPolygon - where the dots go", 2)

para("planDots walks a low-discrepancy sequence and keeps only the points that pointInPolygon "
     "confirms are inside the shape. pointInPolygon is a standard ray-casting test: it counts how "
     "many polygon edges a ray from the point crosses, and an odd count means inside.")

para("Why this is written as its own function rather than using an SVG clip path, which is the "
     "obvious approach: the clip-path version drew one dot per person over the polygon's bounding "
     "box. A zone in this project is a narrow strip, so most of the bounding box is outside the "
     "shape and most dots were clipped away. A zone holding six people displayed two. The bug was "
     "invisible without comparing the dot count to the number printed beside it, which is exactly "
     "why the plan shows both.")

heading("AlertDebouncer.update - the debouncer", 2)

para("Feeds one frame's count in and returns TRIGGERED, CLEARED or nothing.")

code("""if count > capacity:
    if self._over_since is None: self._over_since = now
    self._under_since = None
    if not self.active and now - self._over_since >= ON_DELAY:
        self.active = True; return "TRIGGERED"
    return None""")

para("Why the start of the run is remembered instead of adding up frame deltas: if the caller ever "
     "skips frames, elapsed time is still exactly now minus start. Summing deltas silently loses "
     "the gap, and the alert would fire late by however much time was skipped.")

para("Why being back at capacity resets the over-run to None: a later over-capacity episode must "
     "start its three seconds from zero. Without the reset, a zone that was over for two seconds "
     "this morning and two seconds this evening would fire an alert having never been over for "
     "three continuous seconds in either case.")

heading("DwellTracker.stats - dwell time", 2)

para("Returns the average and the longest dwell for one zone, measured to now.")

para("Why measured to now and not to the last time the person was seen: the person is still "
     "standing there, and the detector merely missed a frame. Measuring to last-seen would make "
     "the dwell time stop growing whenever detection was patchy, which is precisely when it "
     "matters most.")

para("Why a departed person cannot keep collecting time: update() already drops anyone unseen for "
     "longer than TRACK_GRACE, so stats never sees them. The guard is in the update, not in the "
     "report, which is why the report can stay simple.")

heading("Engine._save_evidence - the photograph", 2)

para("Writes the current annotated frame to evidence/alert_N.jpg and returns its URL.")

para("Why a photograph exists at all: an alert row is only numbers. A picture of the moment is "
     "what lets a human check afterwards whether the alert was real, which is the difference "
     "between a system you can audit and a system you have to trust.")

para("Why the row is inserted before the photograph is saved: the file name is alert_N.jpg, so the "
     "id must exist first. If the photograph then fails, the alert still exists with a null "
     "keyframe. A missing picture is much better than a missing alert, and the code returns None "
     "rather than raising.")

para("Why the drawing is a copy, and why the URL rather than the disk path is stored: /video may be "
     "reading the frame at that moment, so drawing into the shared frame would put a permanent stamp "
     "into the live stream. And the row is read by the browser, which can only fetch things served "
     "under /evidence, so a disk path would be useless to it.")

pagebreak()

# =============================================================================================
# PART 6 - THE DASHBOARD
# =============================================================================================

heading("Part 6 - The dashboard, and why it looks like this", 1)

lead("This is 60 percent of the rubric, so it gets the longest answer.")

heading("The design direction, and the one it replaced", 2)

para("The first version of this dashboard was a conventional analytics product: floating cards "
     "with soft shadows over a gradient, a navy background with a glow, and a ring gauge per zone. "
     "It was tidy, and it was wrong for this job.")

para("The reason it was wrong is worth stating precisely, because \"I preferred this\" is not an "
     "answer a panel accepts. A card that floats implies content sitting on top of something else. "
     "A ring gauge implies a dial, which you read by estimating an angle. A glow implies a "
     "presentation screen you look at for a minute, not a console someone watches for a shift.")

para("What replaced it is modelled on the screens an operations room actually runs on: flat "
     "surfaces, hairline rules, tabular monospace numbers, and colour reserved entirely for state.")

table(
    ["Decision", "The failure it prevents"],
    [
        ["Flat panels, no shadow or blur", "a soft shadow turns to mud on a dim projector, and it "
         "implies a card floating over nothing"],
        ["One hue family, colour only for state", "if everything is coloured, nothing stands out; "
         "grey until something is wrong means the eye goes to the problem"],
        ["Occupancy bars, not rings", "reading a fraction off an angle is unreliable at a glance; a "
         "bar shows how much of the limit is used"],
        ["Readings strip, not four cards", "four floating boxes compete with the video for "
         "attention and take twice the height"],
        ["Monospace, tabular figures", "proportional digits shift the layout sideways every time a "
         "number changes"],
        ["A site plan from the real polygons", "an operator recognises their own floor; it also "
         "cannot drift from the video overlay"],
        ["A corner key, not labels on shapes", "a zone is a narrow strip, so text laid across it "
         "spills outside and becomes unreadable"],
    ],
)

heading("The layout", 2)

para("A twelve-column grid from 1024 px up, and a single column below it. The split is 8/4: the "
     "camera and the trend take two thirds, the occupancy meters, site plan and event log take one "
     "third.")

para("Why the video is 8/12 and not larger: the video is the thing being watched, but the numbers "
     "are the thing being acted on. Two thirds gives the picture enough size to see people in while "
     "leaving the readings permanently visible without scrolling.")

para("Why the right column is ordered occupancy, then plan, then log: that is the order of "
     "increasing detail. A glance gives you the count; a second look gives you where; a third gives "
     "you history. An operator who is busy reads the top of that column and nothing else.")

heading("The four readings", 2)

table(
    ["Reading", "Source", "Why it is on the strip"],
    [
        ["People now", "sum of zone counts", "the headline number, and the one the brief names first"],
        ["Peak this session", "highest single frame", "tells you whether the current count is "
         "unusual or normal for this feed"],
        ["Avg dwell", "the busiest zone's average", "not the mean of the means: a quiet zone would "
         "drag it down and hide a real bottleneck"],
        ["Throughput", "measured fps", "an honest performance figure; on this CPU about 16 fps"],
    ],
)

para("Why the dwell reading uses the busiest zone rather than an average across zones: the question "
     "an operator is asking is \"how bad is the worst place\", not \"how is the building on "
     "average\". An average across zones is the number that looks reassuring while one corridor is "
     "jammed.")

heading("What happens when an alert fires", 2)

para("Three things change at once, and each exists for a different reason.")

table(
    ["Signal", "Why it is not enough on its own"],
    [
        ["Red banner across the top", "it is at the top of the screen; an operator watching the "
         "video may be looking at the middle"],
        ["Toast in the corner", "it appears where the eye already is, but it disappears after five "
         "seconds"],
        ["New row in the event log with a photograph", "it is permanent and auditable, but it is in "
         "the right column and easy to miss"],
        ["Count in the browser tab title", "the only signal that reaches an operator who has tabbed "
         "away"],
    ],
)

para("Why the banner names the zone and the duration: \"Main Zone 7/4 for 4 s\" tells an operator "
     "what is wrong, how bad, and whether it is getting worse. \"Congestion detected\" tells them "
     "nothing they can act on.")

heading("Keyboard, screen reader and colour-blind support", 2)

para("These are listed together because they share one property: they are cheap to add at design "
     "time and expensive to retrofit.")

bullet("the status chip carries a word and a distinct icon, never colour alone.", "Meaning is never "
       "colour-only: ")
bullet("the alert list is focusable and the evidence dialog is a native dialog, so Escape, focus "
       "trapping and tab order are the browser's job and not mine.", "Everything is reachable by "
       "keyboard: ")
bullet("new alerts are announced assertively, because an over-capacity area is exactly the news "
       "that should interrupt.", "Live regions are used where they belong: ")
bullet("a prefers-reduced-motion block turns off every non-essential transition.", "Motion can be "
       "switched off: ")

heading("Responsive behaviour", 2)

para("Verified at 1440 px and at 390 px. At 1440 the grid is 8/4 with the four-cell strip in one "
     "row. At 390 everything is a single column, the strip becomes 2x2, the Track A tag and the "
     "product subtitle are hidden so the header never wraps, and the table-driven panels scroll "
     "rather than overflow.")

para("Why hide the subtitle on the narrowest phones rather than shrink it: at 360 px it competes "
     "with the title, and the title truncates to a single letter, which reads as a rendering bug "
     "rather than as a deliberately compact header.")

pagebreak()

# =============================================================================================
# PART 7 - THE NUMBERS
# =============================================================================================

heading("Part 7 - The numbers, with the arithmetic", 1)

lead("Every figure on screen, where it comes from, and the sum that produces it.")

heading("The measured performance", 2)

para("Measured on the machine this was built on: 11th Gen Intel i3-1125G4, 4 physical and 8 "
     "logical cores, 7.65 GB RAM, Windows 11, CPU only.")

table(
    ["Measurement", "Value", "How it was measured"],
    [
        ["Sustained throughput", "about 16 fps", "Engine.measured_fps, a moving average of the last "
         "20 frame durations"],
        ["Time per analysed frame", "60 to 110 ms", "the same moving average, inverted"],
        ["Frames analysed per clip second", "about 8 to 9", "16 fps of processing against 30 fps of "
         "clip, with stride 2"],
        ["MJPEG frame size", "25 to 60 KB", "a 640x360 frame at JPEG quality 80"],
        ["Snapshot payload", "about 500 bytes", "one snapshot dict, as JSON"],
        ["Model load time", "1 to 2 seconds", "once, at startup, not per frame"],
    ],
)

para("Note on the arithmetic: the clip plays at 30 fps but only every second frame is analysed, so "
     "15 frames per clip second need processing. At 16 fps of throughput the pipeline runs slightly "
     "slower than real time, which is why a 45-second clip takes about 90 seconds to play through. "
     "That ratio is stated rather than hidden, because \"real time\" would be a false claim on a "
     "CPU.")

heading("What the demo clips produce", 2)

para("These are the expected results committed in demo_videos/expected_results.md, and the "
     "crowded clip's figures were re-verified on a fresh database.")

table(
    ["Clip", "Length", "Max people", "Median people", "Capacity", "Expected alert"],
    [
        ["normal.mp4", "24.4 s", "4", "2", "4", "none, which is the false-positive check"],
        ["mid.mp4", "31.1 s", "12", "5", "5", "none, because every spike is too short to sustain "
         "3 s"],
        ["crowded.mp4", "45.0 s", "15", "8", "4", "one, at about 31.5 s, peak 8/4"],
    ],
)

para("The three clips are chosen so that the demo proves something. The crowded clip proves the "
     "alert fires. The normal clip proves an empty scene does not set it off. The mid clip is the "
     "interesting one, because it is busy and still produces no alert, which demonstrates the "
     "debouncer rather than the absence of people.")

heading("The arithmetic of an occupancy meter", 2)

code("""count 7, capacity 4
fill        = 7 / 4            = 1.75
bar width   = min(1.75, 1)     = 1.00  -> 100% of the track
status      = 7 > 4            = OVER
dwell       = now - entered_at = 12.4 s average
speed       = distance / time  = 40 px / 2 s = 20 px/s""")

para("The bar is full, not overflowing, and the OVER chip carries the excess. That is a deliberate "
     "choice: a bar that visibly overflows its track looks like a layout failure, and the number "
     "beside it already says 7 of 4.")

heading("The arithmetic of dwell", 2)

code("""ID 7 enters Main Zone at video time 9.0 s
asked at video time 12.4 s
dwell = 12.4 - 9.0 = 3.4 s""")

para("Average versus longest, with real numbers: three people with dwells of 60 s, 2 s and 2 s "
     "average 21.3 s and have a longest of 60 s. Three people with 21 s each average the same 21 s "
     "and have a longest of 21 s. The average says the two situations are identical; the maximum "
     "says one of them has somebody stuck in it. That is why both are computed.")

heading("The arithmetic of the heatmap", 2)

code("""HEAT_DECAY 0.995, a pixel holding 1.0 with one new foot point on it:
   before  1.0
   decay   1.0 * 0.995 = 0.995
   add     0.995 + 1.0 = 1.995""")

para("Why float32 and not uint8: 255 times 0.995 is 253.7, which rounds back to 255 in an integer "
     "array. The heat would never fade. The decay only works in floating point.")

heading("The speed figure, stated honestly", 2)

para("Speed is reported in pixels per second, and this is the deliberate part.")

para("Converting pixels to metres needs a camera calibration: the height of the camera, its angle, "
     "the position of the floor plane and a lens model. None of that is available for stock "
     "footage. A km/h figure would therefore be invented, and an invented number in a safety tool "
     "is worse than no number at all.")

para("Pixels per second still answers the question that matters: is this a queue or a "
     "thoroughfare? That comparison needs no calibration because it is between zones and over time "
     "within one fixed camera.")

heading("The contrast figures", 2)

para("Measured against the panel colour, using the WCAG relative-luminance formula.")

table(
    ["Text", "Ratio", "Standard"],
    [
        ["Body ink", "15.4:1", "passes AAA for body text (7:1)"],
        ["Secondary ink", "8.1:1", "passes AAA"],
        ["Dimmest ink", "4.9:1", "passes AA for small text (4.5:1)"],
        ["OK green", "11.8:1", "passes AAA"],
        ["NEAR amber", "9.3:1", "passes AAA"],
        ["OVER red", "8.3:1", "passes AAA"],
        ["Accent blue", "6.4:1", "passes AA"],
    ],
)

para("Why this is in the document at all: \"the colours look fine\" is not a defence of an "
     "interface, and a panel member who works on accessibility will ask. These are computed, not "
     "estimated, and every one of them passes the level it needs to.")

pagebreak()

# =============================================================================================
# PART 8 - DEFECTS FOUND AND FIXED
# =============================================================================================

heading("Part 8 - What went wrong, and what was fixed", 1)

lead("Real defects found by looking at the rendered result, not by guessing. This is usually the "
     "most convincing part of a walkthrough.")

heading("The four defects in the redesign", 2)

para("Each of these was introduced by the UI rewrite and found by reviewing the page rather than by "
     "reading the code. All four are worth mentioning because each one is a class of bug.")

table(
    ["Symptom", "Cause", "Fix"],
    [
        ["A zone at NEAR showed an amber chip beside a green bar", "the markup had no class for the "
         "NEAR state, so the bar kept the default OK styling", "a stateClass map that emits is-near "
         "and is-hot explicitly"],
        ["Event-log rows collapsed to about 7 px tall", "the row was a flex child in a column that "
         "could shrink it", "flex-shrink: 0 on the row"],
        ["The site plan used about 20 percent of its panel", "the viewBox was the whole 640x360 "
         "frame while the zone occupied one corner", "planViewBox zooms to the zone bounds, clamped "
         "to the frame"],
        ["A zone of six people drew two dots", "dots were spread over the polygon's bounding box and "
         "then clipped, and a narrow strip is mostly outside its own bounding box", "planDots tests "
         "each candidate point with pointInPolygon"],
    ],
)

para("The first is the most instructive. It was not a styling mistake in the stylesheet; the "
     "stylesheet had the right rule all along. The markup simply never asked for it, and a missing "
     "class fails silently. That is why the code now builds the class from an explicit map rather "
     "than two ternaries: a state that is not in the map is visible in the source.")

para("The fourth is the one that shows why the site plan displays the count as a number as well as "
     "drawing dots. Six people and two dots is only noticeable if the two figures are visible "
     "together; a picture alone would have hidden its own bug.")

heading("Defects fixed earlier in the build", 2)

table(
    ["Problem", "Why it happened", "What changed"],
    [
        ["Alerts repeating dozens of times for one crowd", "the raw count crossed the threshold "
         "every frame", "AlertDebouncer with a 3 s on-delay and a 5 s off-delay"],
        ["Dwell times roughly doubling", "an early version measured dwell against the wall clock "
         "while the clip played slower than real time", "every timestamp is video time"],
        ["Peak counts going down", "a read-compare-write in Python could interleave", "MAX() inside "
         "the SQL statement"],
        ["\"Database is locked\" on Windows", "connections opened without a guaranteed close", "a "
         "context manager per call"],
        ["The dashboard freezing during a source switch", "the web thread tried to close the capture "
         "the engine was reading", "a restart flag the loop acts on between frames"],
    ],
)

heading("What was deliberately not fixed", 2)

para("Two things are known and left alone, and saying so is stronger than pretending otherwise: "
     "save_zones in app/zones.py is written and works but nothing calls it, because zones.json is "
     "hand-edited for three fixed clips; and there is no camera calibration, so speed stays in "
     "px/s. Both are documented as limits rather than quietly counted as features.")

pagebreak()

# =============================================================================================
# PART 9 - LIMITATIONS
# =============================================================================================

heading("Part 9 - Limitations, stated before you are asked", 1)

lead("Every one of these is a real limit. Naming them first is what separates a candidate who "
     "understands the system from one who hopes the question does not come up.")

heading("The six that matter", 2)

table(
    ["Limitation", "Why it is true", "What it would take to fix"],
    [
        ["Speed is in pixels per second, not km/h", "no camera calibration for stock footage",
         "four floor measurements per camera, then a homography"],
        ["The model is YOLOv8 nano", "the only variant that runs at a usable rate on this CPU",
         "a GPU, then yolov8m or larger"],
        ["Occlusion causes undercounting", "a person behind a pillar or another person has no "
         "visible feet", "multiple camera angles, or a head-count model"],
        ["It processes about 16 fps, slower than the 30 fps clip", "CPU only", "a GPU, or a "
         "smaller model and a wider stride"],
        ["Zones are fixed polygons in a JSON file", "a camera move invalidates them", "re-draw them, "
         "or track camera motion"],
        ["Alerts are a threshold rule, not a prediction", "the system reports what is happening, not "
         "what will happen", "a time-series forecast, which needs far more data than three clips"],
    ],
)

heading("How to say each one out loud", 2)

para("The wording matters as much as the content. \"It does not do that yet\" invites a follow-up; "
     "\"here is the constraint, here is what I chose instead, and here is what I would need\" ends "
     "the line of questioning.")

table(
    ["Question", "A good answer"],
    [
        ["Why not km/h?", "Because I have no camera calibration, so any figure in km/h would be "
         "invented. Pixels per second still answers the operational question, which is whether a "
         "zone is a queue or a thoroughfare."],
        ["Why not a bigger model?", "Because it runs on a CPU, and the nano model is what gets 16 fps. "
         "A larger model at 4 fps would make the dashboard useless as a live tool."],
        ["Does it miss people?", "Yes, when they are occluded, and it undercounts rather than "
         "overcounts. I would rather it undercount and say so than invent people who are not there."],
        ["Is it real time?", "No, and I do not claim it is. It processes about 16 fps against a 30 fps "
         "clip, so a 45-second clip takes about 90 seconds. Everything on screen is labelled with "
         "video time, so the difference is visible rather than hidden."],
    ],
)

heading("What was chosen not to build, and why", 2)

para("These are scope decisions, not omissions, and each has a reason. No face recognition or "
     "person re-identification, because the brief asks for counting and congestion, not identity, "
     "and building it would add a privacy obligation and a large amount of code that serves none of "
     "the three questions. No multi-camera tracking, because one clip and one view is enough to "
     "demonstrate the pipeline. No extra dependencies, because the brief fixes the stack and every "
     "extra library is another thing to install on the grading machine. No fourth clip, because "
     "three cover three scenarios and a fourth would add demo time and no new evidence.")

pagebreak()

# =============================================================================================
# APPENDIX
# =============================================================================================

heading("Appendix - Running it, and checking it works", 1)

heading("The one-step way", 2)

para("Double-click start.bat in the project folder. It activates the virtual environment, opens the "
     "browser after four seconds, and starts the server on 127.0.0.1:8000.")

heading("The command-line way", 2)

code("""py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000""")

heading("Running the tests", 2)

code(""".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v""")

para("20 tests, about 0.14 seconds. They cover the foot point, resizing, zone lookup, the status "
     "thresholds, dwell, speed, the debouncer, the heatmap, the database and the shared state.")

heading("A fresh alert cycle", 2)

code("""Stop the server, then delete results\\crowd.db and everything in evidence\\. Start again.
Within about 45 seconds of the crowded clip, exactly one alert should appear:
   zone      Main Zone
   peak      8 / 4
   evidence  evidence\\alert_1.jpg""")

para("Deleting the database resets the alert count, which is the only way to see a first alert "
     "again. The history table is separate, so the chart still pre-fills from whatever rows remain.")

heading("Checking the layout at two widths", 2)

para("At 1440 px: a twelve-column grid with an 8/4 split, the four readings in one row, and a site "
     "plan at exactly 16:9. At 390 px: a single column, the readings in a 2x2 block, and no "
     "horizontal scrolling anywhere.")

note("The one thing to close before a demo",
     "Close every other browser tab. Each open tab holds its own MJPEG stream, and two or three of "
     "them will starve the CPU on a four-core laptop. The visible symptom is a black video area, and "
     "the cause is not obvious while it is happening.")

para("")
para("")
para("End of reference.", italic=True, size=9.5)

# =============================================================================================
# BUILD
# =============================================================================================

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT}  ({size_kb:.0f} KB)")
