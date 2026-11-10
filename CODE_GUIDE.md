# Crowd Density and Bottleneck Analytics — Code Guide

This is the document to study before the interview. It explains what the app is, how the
pieces fit together, and what every file and function does, in plain English with small
numbers you can repeat out loud.

Read it in this order:

1. Part 1 — the 60-second pitch
2. Part 2 — the architecture (one diagram, four layers)
3. Part 3 — the data flow, frame by frame
4. Part 4 — file by file, function by function
5. Part 5 — the numbers in the app (with worked arithmetic)
6. Part 6 — the design decisions and why they are defensible
7. Part 7 — the PDF requirements, mapped
8. Part 8 — likely questions and short answers

---

# Part 1 — The 60-second pitch

> A shop, station or campus corridor gets crowded. By the time a human notices on a camera
> monitor, the queue has already formed. This app watches a video feed and answers three
> questions continuously: **how many people are in each area**, **how long are they staying**,
> and **are they moving or stuck** — and it raises a warning the moment an area goes over its
> safe capacity.
>
> It is one Python process. A background thread reads the video, runs YOLOv8 nano to find
> people and ByteTrack to give each person a stable ID, then counts them inside hand-drawn
> zones. A FastAPI web server sends the annotated video and the live numbers to a dark-mode
> dashboard in the browser.
>
> Everything runs on a CPU, offline, with open-source parts only.

Three sentences if you are very short on time:

- **Track A** of the brief: crowd density and bottleneck analytics.
- **Stack**: Python + YOLOv8n/ByteTrack (ultralytics) + OpenCV + FastAPI + SQLite, plain HTML/Tailwind/Chart.js.
- **Result**: live annotated video, zone gauges, headcount chart, congestion banner, and a saved alert history with evidence photos.

---

# Part 2 — The architecture

The PDF (slide 16) asks for a modular pipeline that keeps vision processing separate from the
operator interface. That is exactly the shape of this project: **four layers, one direction of
data flow.**

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1 — INPUT                                                │
│  demo_videos/crowded.mp4, mid.mp4, normal.mp4                   │
│  OpenCV VideoCapture reads one frame at a time                  │
└────────────────────────────┬────────────────────────────────────┘
                             │  BGR frame (1280x720) → resized to 640 wide
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2 — VISION AND RULES          (app/vision.py, zones.py,  │
│                                        app/analytics.py)        │
│  YOLOv8 nano   → finds person boxes                             │
│  ByteTrack     → gives each person a stable ID (1, 2, 3, ...)   │
│  zones.json    → is this person's foot inside a zone?           │
│  analytics     → dwell time, speed, heatmap, alert debounce     │
└────────────────────────────┬────────────────────────────────────┘
                             │  a "snapshot" dict + the drawn frame
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3 — BACKEND AND STORAGE       (app/engine.py, db.py,      │
│                                        app/main.py)             │
│  Engine thread  → runs the loop forever, publishes SharedState  │
│  SQLite         → alerts table + headcount table                │
│  FastAPI        → REST for history, WebSocket for live numbers, │
│                   MJPEG for the video stream                    │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP + WebSocket on 127.0.0.1:8000
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 4 — WEB DASHBOARD             (static/index.html,        │
│                                        app.js, style.css)       │
│  Live video with boxes + zones + heatmap                        │
│  4 KPI tiles, zone gauges, headcount chart, alert log           │
│  Congestion banner, toast, evidence photo modal                 │
└─────────────────────────────────────────────────────────────────┘
```

### The one idea that makes this architecture work

**The slow part and the fast part are separated by one small object.**

Reading a frame and running YOLO takes about **60–110 ms**. A browser asking for the latest
numbers must be answered in **microseconds**. If the web request did the vision work, the page
would freeze.

So there are exactly two threads:

| Thread | Job | Speed |
| --- | --- | --- |
| **Engine** (background) | read frame → detect → count → save → publish | ~10–16 frames/second |
| **Web** (FastAPI) | serve whatever the engine last published | instant |

They meet only at `SharedState`, protected by one lock. The engine **writes**; web requests
**read copies**. No request ever waits for the model. That is the whole trick, and it is worth
saying out loud in the interview.

### Why one lock and not several

The video and the numbers must describe the **same moment**. With separate locks a page could
show a frame from video-second 10.0 next to a count from 10.5 s, and the boxes would not match
the numbers beside them. `SharedState.get()` returns frame, people and snapshot **together**
inside one locked block, so they are always consistent.

---

# Part 3 — The data flow, frame by frame

Follow one frame through the system. This is the sequence you will be asked to narrate.

```
frame arrives          frame_index 240
      │
      ├─ every STRIDE'th frame only ──────── STRIDE = 2 → analyse frame 240, skip 241
      │
      ├─ resize to 640 wide ─────────────── 1280x720 becomes 640x360
      │
      ├─ detector.track(frame) ──────────── YOLO finds people, ByteTrack assigns IDs
      │                                      → [Person(7, box, 0.91, foot=(120,200)), ...]
      │
      ├─ time = frame_index / fps ───────── 240 / 29.97 = 8.01 s of VIDEO time
      │
      ├─ count_by_zone(zones, people) ───── feet inside "Main Zone" → {"Main Zone": [p7, p9]}
      │
      ├─ dwell.update(time, members) ────── remember when ID 7 entered the zone
      ├─ heatmap.add(feet) ──────────────── add 1.0 at each foot pixel
      ├─ speed.update(time, people) ─────── distance moved ÷ time since last seen
      │
      ├─ debouncer.update(...) ──────────── has it been over capacity for 3 s? → alert?
      │        └─ if TRIGGERED: write DB row, save evidence photo
      │
      ├─ every 2 video seconds ──────────── write headcount rows to SQLite
      │
      └─ state.set(frame, people, heat, snapshot)   ← published, under one lock
                    │
                    ▼
        WebSocket sends the snapshot         /video renders a JPEG
        to the browser 2x per second         up to 15x per second
```

### Critical detail: video time, not wall-clock time

Every analytics number uses **video time** — `frame_index / fps` — not `time.time()`.

Why it matters: the demo replays a recording at roughly 16 fps, but the recording itself is
29.97 fps. If dwell used the wall clock, a person standing still for 10 seconds of video would
report about 18 seconds of dwell, and the alert delays would be wrong too. Using video time
makes "3 seconds over capacity" mean 3 seconds **of the footage**, which is what the operator
sees on screen and what the PDF's demo example describes.

---

# Part 4 — File by file, function by function

The project has **7 Python files, 3 web files, 1 config file, 1 test file**. That is the whole
codebase. Learn this section and you can answer any code question.

```
crowd-analytics/
├── app/
│   ├── config.py       ← all tunable numbers (no magic numbers anywhere else)
│   ├── vision.py       ← YOLO + ByteTrack, returns Person objects
│   ├── zones.py        ← zone polygons, capacity, the OK/NEAR/OVER rule
│   ├── analytics.py    ← dwell, speed, heatmap, alert debounce
│   ├── db.py           ← SQLite: alerts + headcount history
│   ├── engine.py       ← the background video loop + SharedState
│   └── main.py         ← FastAPI routes (the web layer)
├── static/
│   ├── index.html      ← the dashboard markup
│   ├── app.js          ← fetches data, draws gauges/chart/alerts
│   └── style.css       ← the dark command-centre theme
├── tests/
│   └── test_pipeline.py ← 20 tests, one per important rule
├── zones.json          ← zone polygons + capacities per clip
├── start.bat           ← double-click launcher
└── requirements.txt    ← pinned dependencies
```

---

## 4.1 `app/config.py` — one place for every number

**Why it exists:** the brief forbids magic numbers. Every threshold in the app is a named
constant here, so you can change behaviour by editing one file and you can always point at a
name instead of a stray `0.35` in a function.

| Constant | Value | What it controls |
| --- | --- | --- |
| `MODEL_PATH` | `"yolov8n.pt"` | which YOLO weights to load |
| `CONF` | `0.35` | minimum confidence for a box to count as a person |
| `IMGSZ` | `640` | the square size the model sees |
| `PERSON_CLASS_ID` | `0` | COCO class 0 = person; we ignore all 79 other classes |
| `FRAME_WIDTH` | `640` | every frame is resized to this width |
| `STRIDE` | `2` | analyse every 2nd frame |
| `ON_DELAY` | `3.0` s | how long over capacity before an alert fires |
| `OFF_DELAY` | `5.0` s | how long back to normal before it clears |
| `NEAR_RATIO` | `0.8` | fraction of capacity that shows amber "NEAR" |
| `HEAT_DECAY` | `0.995` | how fast old heat fades |
| `HEAT_BLUR_FRACTION` | `0.05` | blur width as a fraction of frame width |
| `HEAT_MASK_RATIO` | `0.08` | below this fraction of peak, draw nothing |
| `HEAT_OVERLAY_ALPHA` | `0.5` | how strongly heat tints the video |
| `TRACK_GRACE` | `2.0` s | how long a lost track is remembered |
| `JPEG_QUALITY` | `80` | stream image quality |
| `MJPEG_MAX_FPS` | `15` | cap on the video stream rate |
| `WS_INTERVAL` | `0.5` s | how often the WebSocket pushes numbers |
| `HEADCOUNT_INTERVAL` | `2.0` s | how often a headcount row is saved |
| `FPS_WINDOW` | `20` | frames used for the moving-average FPS |
| `DEFAULT_SOURCE` | `"crowded.mp4"` | which clip plays on startup |

Paths are all built from `BASE_DIR = Path(__file__).resolve().parent.parent`, so the app works
from any working directory and never hard-codes `C:\...`.

**Small numbers to remember:** `CONF 0.35` means the model must be at least 35% sure.
`STRIDE 2` means we look at every second frame, which nearly doubles throughput at the cost of
slightly choppier motion tracking.

---

## 4.2 `app/vision.py` — the eyes

**Why it exists:** it is the only file that knows what YOLO is. Everything else asks for
"people" and gets a clean list. If you swapped YOLOv8 for another detector, this is the only
file that would change.

### `Person` (dataclass)

One detected person in one frame. Four fields:

- `track_id` — the stable number ByteTrack gives this person (`7`, `9`, ...)
- `box` — `(x1, y1, x2, y2)`, the rectangle corners in the resized frame
- `conf` — confidence, 0 to 1
- `foot` — `(x, y)`, the **bottom-centre** of the box

### `foot_point(box)`

Returns the bottom-centre of a box.

**Why:** a box's centre sits around the person's chest, which floats up and down as they move.
The **feet** sit on the floor, and floor positions are what zone polygons are drawn around.

> Example: box `(100, 50, 140, 200)` → `((100+140)//2, 200)` = `(120, 200)`.

*This is a great answer to "why bottom-centre and not centre?" — because zones are floor areas.*

### `resize_frame(frame, width)`

Shrinks or grows a frame to a fixed width, keeping the aspect ratio.

**Why:** a fixed width makes detection speed, drawing coordinates and the browser stream
predictable. Keeping the ratio stops people looking stretched.

> Example: 1280×720 at width 640 → height `720 × 640 / 1280` = 360. So 640×360.

It uses `INTER_AREA` when shrinking (cleaner) and `INTER_LINEAR` when enlarging (less blur).

### `Detector.track(frame)`

The core call. It runs:

```python
model.track(frame, persist=True, tracker="bytetrack.yaml",
            classes=[0], conf=0.35, imgsz=640, verbose=False)
```

- `persist=True` — keep tracker state between calls, so IDs stay stable across frames
- `classes=[0]` — only class 0 (person); ignore bags, cars, dogs
- `conf=0.35` — the threshold from config
- returns a list of `Person`

If `boxes.id is None` the tracker produced no tracks, so it returns `[]` instead of crashing.

### `Detector.reset()`

Restarts tracking IDs at 1. Needed when switching clips, otherwise clip 2 would continue
numbering from clip 1 and the dwell timings would be nonsense.

### YOLO and ByteTrack in one sentence each

- **YOLOv8 nano** — a neural network that looks at one image and outputs boxes with class
  labels and confidences. "Nano" is the smallest variant: ~3 M parameters, fast enough for CPU.
- **ByteTrack** — a tracker. It matches this frame's boxes to last frame's boxes by position
  and motion, so the person at `(120, 200)` now is recognised as the same person at
  `(124, 198)` a moment ago. That is what turns "7 boxes" into "7 people, one of whom has been
  here 12 seconds".

---

## 4.3 `app/zones.py` — geometry and the status rule

**Why it exists:** the dashboard, the counting and the alert all ask the same question —
*"which zone is this person in, and is it full?"* — and they must all get the same answer.
Keeping the geometry and the rule in one file means it cannot drift.

### `Zone` (dataclass)

`name`, `capacity`, `polygon`. The polygon is a numpy array shaped `(N, 1, 2)` of int32,
because that is the exact format `cv2.pointPolygonTest` and `cv2.fillPoly` expect.

### `make_polygon(points)`

Turns `[(10,10), (20,10), (20,20)]` into that `(N,1,2)` array. One conversion, one place.

### `load_zones(path, source_name)`

Reads the zones for **one clip** from `zones.json`.

**Why per clip:** every clip has a different camera angle, so a polygon drawn for one video
would be in the wrong place on another. A missing entry raises a clear error instead of
silently drawing nothing (which would look like "nobody is ever in a zone").

### `zone_of(zones, point)`

Returns the first zone containing the point, or `None`.

`cv2.pointPolygonTest(..., measureDist=False)` returns `>= 0` for inside-or-on-edge, `< 0` for
outside. "First match wins" because polygons can overlap, and the most important zone is listed
first in `zones.json`.

### `count_by_zone(zones, people)`

Groups people by the zone their **feet** are in. Starts every zone at an empty list so zones
with nobody in them still appear (the dashboard must show `0 / 5`, not hide the zone).

> Example: person A's feet at (100,200) inside "Main Zone", person B's at (600,40) outside
> every zone → `{"Main Zone": [A]}`. B is in no list.

### `status_for(count, capacity)` — the most important small function

```python
if count > capacity:            return "OVER"   # strictly more than capacity
if count >= 0.8 * capacity:     return "NEAR"   # 80% or more
return "OK"
```

**One rule, three callers:** the video colour, the API value and the test all use it, so the
gauge can never say "OK" while the alert says "over".

> Example with capacity 10: 7 → OK, 8 → NEAR, 10 → NEAR, 11 → OVER.
>
> Note: exactly full (10/10) is still **NEAR**, not OVER. "Over capacity" means more people than
> it is meant to hold.

### `draw_zones(frame, zones, counts)`

Draws every zone on a **copy**: translucent fill, outline, and a label like `Main Zone  6/5`.
The colour comes from `status_for`, so a zone turns amber before it is full and red once it is
over. Drawing on a copy matters — drawing on the original would slowly paint boxes into the
video we are measuring.

### `save_zones(path, source_name, zones)` and `_format_zone(entry)`

Write one clip's entry back to `zones.json`, keeping the other clips. The custom formatting
puts each `[x, y]` pair on one line so an 8-corner zone is readable rather than 48 lines of
numbers.

---

## 4.4 `app/analytics.py` — memory over time

**Why it exists:** counting people in a frame is easy. The interesting answers need to remember
the past — *how long has this person been here?*, *where do crowds keep forming?*, *has this
zone really been full for 3 seconds?*. Each question is one small class.

**Every timestamp entering this file is VIDEO time**, never the wall clock. A replay is a
recording; a wall clock would make every dwell and alert timing meaningless.

### `DwellTracker`

Remembers, per **`(zone, track_id)`**, when someone entered and when they were last seen.

**Why per zone and not per person:** one person can walk from a quiet zone into a busy one. The
second zone's dwell must start when they cross the line, not when they first appeared on screen.

- `update(now, members)` — starts a clock for new visitors, refreshes `last_seen` for returning
  ones, and **forgets** anyone unseen for more than `TRACK_GRACE` (2 s).
- `stats(zone, now)` — returns `(average, longest)` dwell in seconds.

> Example: ID 7 enters "Main Zone" at video 9.0 s. At 12.4 s the average dwell is
> `12.4 − 9.0 = 3.4 s`.

**Why report both average and longest:** an average hides a bottleneck. One person waiting 60 s
among nine waiting 2 s averages 8 s — the same average as ten people waiting 8 s each, but a
completely different operational situation. The **maximum** exposes the person who is actually
stuck.

### `SpeedTracker` — the "movement velocity" requirement from the PDF

Estimates how fast each person is moving, in **pixels per second**.

**Why pixels and not km/h:** converting pixels to metres needs a camera calibration (where the
floor is, how far away, at what angle). We do not have that. Pixels per second is honest, needs
no extra data, and is still comparable within one clip: a zone where people move at 5 px/s is
far more congested than one where they move at 40 px/s.

**How it works:** keep `track_id → (last_time, last_foot)`. On the next sighting, speed is
`distance ÷ elapsed time`.

> Example: foot at (100,200) at 1.0 s, then (140,200) at 3.0 s. Distance 40 px, elapsed 2 s →
> **20 px/s**.

A person on their **first** frame has no earlier position, so they report no speed rather than a
fake `0`. Stale IDs are dropped after `TRACK_GRACE`.

`_distance(a, b)` uses `np.hypot` — Pythagoras, because the diagonal of a step is genuinely
shorter than `|dx| + |dy|`.

> Example: (0,0) to (30,40) → `sqrt(900 + 1600) = 50` px.

### `HeatmapAccumulator` — the density heatmap

Builds a "where do people stand?" picture by piling up foot points over time.

- `add(points)` — multiply the whole map by `HEAT_DECAY` (0.995), then `+1.0` at each foot pixel.
- `layer()` — blur, normalise, colour, and build a mask.
- `overlay(frame, alpha)` — blend the heat onto a copy, only inside the mask.

**Why decay:** a plain running total would make one busy minute glow forever. Decay means the
picture always describes the *recent* past.

> Example with 0.995: a pixel holding 1.0 becomes 0.995 after one frame, ≈0.951 after ten, and
> ≈0.61 after one hundred frames.

**Why float32 and not uint8:** `0.995 × 255` rounds down every frame in integer maths, so the
heat would vanish. Floats keep the fractions.

**Why blur:** one foot point is one pixel — invisible on video. A Gaussian blur (kernel ≈ 5% of
frame width, forced odd because OpenCV refuses even kernels) turns it into a soft blob;
overlapping blobs become a visible hot area.

**Why normalise:** raw values could be 2 or 200 depending on clip length. Dividing by the
current maximum makes colour mean "hot *compared with now*", which is what a viewer expects.

**Why a mask:** without it the entire frame would be tinted blue, including empty floor, and the
video underneath would be unreadable. `HEAT_MASK_RATIO 0.08` means "only draw where you have at
least 8% of peak heat".

> Example: values 0.0, 0.5, 2.0 normalise to 0, 64, 255. With ratio 0.08 the threshold is 20, so
> only the last two pixels are drawn.

### `AlertDebouncer` — the rule that stops alert spam

**Why it exists:** the head count jumps by ±1 constantly (a detection misses, someone steps on a
line). Alerting on every over-capacity frame would produce dozens of alerts for one real
problem.

The rule: fire only after the zone has been over capacity for `ON_DELAY` (3 s); clear only after
it has been back to normal for `OFF_DELAY` (5 s).

- `update(now, count, capacity)` → `"TRIGGERED"`, `"CLEARED"`, or `None`
- `over_for` → how many seconds the current over-capacity run has lasted

**Why time-based runs instead of counting frames:** with `STRIDE 2` frames are not equally
spaced in seconds, so counting frames would make "3 seconds" last 3 frames.

**Why remember the run *start* instead of adding up deltas:** if the caller skips frames or the
video jumps, `now − run_start` is still exactly right; summing deltas silently loses the gap.

> Example with `ON_DELAY 3 s` and capacity 5: counts over 6 lasting 1 s produce nothing. The same
> counts lasting 4 s produce **exactly one** TRIGGERED, however many frames pass.
>
> Example with `OFF_DELAY 5 s`: over at 0 s → fires at 3 s. Back under at 4 s → clears at 9 s.

---

## 4.5 `app/db.py` — the history

**Why a separate module:** two things use the tables — the engine writes while the video runs,
the API reads for the dashboard. Keeping every SQL statement in one file means there is exactly
one place to look when a number seems wrong.

### The two tables

```sql
alerts     (id, zone, source, started_at, video_ts, ended_at, peak_count, capacity, keyframe)
headcount  (ts, zone, count)
```

`alerts` is one row per over-capacity **episode**. `headcount` is a sample every 2 video seconds
for the chart.

### Two storage decisions worth defending

1. **Every value is passed as a `?` parameter**, never formatted into the SQL string. A zone
   name or file name is user-controlled; string formatting would open SQL injection and also
   break on any name containing a quote.
2. **Each function opens its own short-lived connection.** SQLite objects cannot be shared
   between threads, and the engine runs in a different thread from FastAPI. A per-call
   connection sidesteps that entirely, and each call is one tiny query, so the cost is
   negligible.

### Functions

| Function | What it does |
| --- | --- |
| `connect()` | context manager: open, `yield`, commit, always close |
| `init_db()` | `CREATE TABLE IF NOT EXISTS` — safe on every start |
| `utc_now_iso()` | wall-clock time as an ISO-8601 UTC string |
| `insert_alert(...)` | insert one alert, **return its id** |
| `end_alert(id)` | stamp `ended_at` |
| `update_peak(id, n)` | `SET peak_count = MAX(peak_count, ?)` |
| `set_keyframe(id, url)` | attach the evidence photo URL |
| `list_alerts(limit)` | newest first, for the feed |
| `add_headcount(...)` | append one sample |
| `headcount_since(minutes)` | samples from the last N minutes, **oldest first** |

**Why `insert_alert` returns the id:** the evidence photo is named `alert_<id>.jpg`, so the id
must exist before the file can be named. Insert first, then save the picture, then update the
path. If the photo fails, the alert still exists with a null keyframe — a missing picture is far
better than a missing alert.

**Why `MAX(peak_count, ?)` in SQL rather than read-compare-write in Python:** one statement
cannot be interrupted between the read and the write, so a concurrent writer can never *lower* a
peak that another writer already raised. The busiest moment is the evidence.

**Why `started_at` (wall clock) AND `video_ts` (video time):** they answer different questions.
`started_at` = "when did this happen in real life?" for the history. `video_ts` = "where in the
clip?" so a reviewer can jump to that moment. Both are worth storing.

**Why ISO-8601 strings for timestamps:** ISO-8601 in UTC sorts alphabetically in the same order
it sorts in time, so `WHERE ts >= ?` and `ORDER BY ts` both work with **no date parsing per row**.

---

## 4.6 `app/engine.py` — the loop and the hand-over

This is the largest file (624 lines) and the one most likely to be probed. It has two jobs:
run the video loop, and own `SharedState`.

### `empty_snapshot(source)`

Returns a valid all-zero snapshot: `ts 0, fps 0, total_people 0, zones []`.

**Why:** a browser connects to `/ws` immediately, while YOLO is still loading. Sending `{}`
would break the contract and force every client to guard against missing keys. Sending a
well-formed "nothing yet" snapshot means the dashboard renders its first frame with no special
cases.

### `SharedState` — the heart of the architecture

- `set(frame, people, heat, snapshot)` — replaces whichever pieces are supplied, under one lock.
  Arguments are optional so a caller passes only what changed.
- `get()` — returns `(frame_copy, people_copy, snapshot_deepcopy)` **together**, under one lock.
- `get_heat()` — returns the cached heat layer, or `None`.

**Why copies on the way out:** the engine keeps writing into its own frame buffer. A reader
holding a reference would see the picture change underneath it — or change halfway through the
JPEG encoder, producing a torn image.

**Why `deepcopy` for the snapshot:** it nests dicts and lists that a reader may walk through.

**Why `get()` returns everything in one call:** three separate getters could interleave with an
engine update and return a frame from one moment and a snapshot from another.

**Why the heat layer is computed once per frame:** `/video` renders up to 15 frames a second.
Re-blurring a full-size heatmap for each request would be wasted work, so the engine computes
`layer()` once and every render reuses it.

### `list_clips()`

Returns the `.mp4` filenames in `demo_videos/`, sorted.

**Why an allow-list and not a path check:** `set_source` must never accept a path from the
browser. Building the list from the actual folder means the only values that can ever be
accepted are names this function already returned. `POST /api/source {"name": "../../zones.json"}`
is rejected because it is not on the list.

### `source_fps(capture)`

Reads the clip's frame rate, falling back to 25 if the metadata is broken.

**Why:** every time in the snapshot is `frame_index / fps`. A NaN or zero would make all of them
nonsense, so a sane fallback beats crashing on a bad download.

### `Engine(threading.Thread)` — the loop

It is a `Thread` subclass with `daemon=True`, so a closed terminal never leaves a hidden process
holding a video file open.

- `set_source(name)` — **only sets a flag** (`_restart_requested`). Why: this runs in a web
  request thread; closing the capture from here would yank the file handle out from under the
  video loop. The loop notices the flag at the top of its next frame and rebuilds itself there.
- `run()` — `while True: self._play_clip(...)`, wrapped in try/except. Why forever: when the
  footage ends, replaying it is more honest than freezing on the last frame with a crowd that
  never moves. Why try/except: a crashed thread would leave a permanently frozen dashboard with
  no explanation.
- `_play_clip(source_name)` — plays one clip start to finish. Everything that remembers
  (detector tracks, dwell, speed, heat, debouncers) is **rebuilt here**, so a replay starts from
  a clean slate instead of inheriting the previous loop's state.

Inside `_play_clip`, the frame loop:

```python
while not self._restart_requested:
    if not capture.grab(): break          # advance cheaply, decode nothing
    if frame_index % STRIDE == 0:         # every 2nd frame
        ok, frame = capture.retrieve()    # only now decode
        frame = resize_frame(frame, 640)
        ... detect, count, read analytics ...
        self.state.set(frame, people, heat, snapshot)
    frame_index += 1
```

**`grab()` vs `retrieve()`:** `grab()` moves the read pointer forward without decoding;
`retrieve()` decodes the frame. Using `grab()` on skipped frames is what makes `STRIDE 2` save
real time instead of just saving the model call.

**The `finally` block** releases the capture and closes any open alerts even if a frame raised.
On Windows that is what stops the clip staying locked for the next replay.

### `_update_alerts(...)`

Feeds each zone's count into its own `AlertDebouncer` and acts on the events.

**Why it returns `new_alert`:** the snapshot must carry the alert for exactly one publication, so
the alert travels from here to the snapshot builder instead of being stored and cleared later.

**Why peaks are tracked in memory first:** a DB write on every frame while an alert is open
would be eight connections a second for a value that almost never changes. It is written only
when the peak actually rises.

### `_open_alert(...)` / `_finish_alert(...)` / `_close_alerts(...)`

Open = insert the row, save the evidence photo, remember the id. Finish = stamp `ended_at`, drop
the in-memory peak. Close-all = called when a clip stops, so no alert looks live forever for a
video that is not even playing.

### `_save_headcounts(counts)`

Writes one row per zone **plus a total row** under the reserved name `"ALL"`, every 2 video
seconds.

**Why a total row:** the chart shows "people in the picture" and "people in this zone" on
different scales, and the total cannot be summed from per-zone rows without one query per
refresh.

### `_save_evidence(alert_id, people, zones, counts, now)`

Draws boxes, foot dots, zones and an `"ALERT 3  31.5s"` stamp onto a copy, writes
`evidence/alert_<id>.jpg`, and returns the **URL** (`/evidence/alert_3.jpg`), not the disk path —
the browser can only fetch what is served under `/evidence`.

### `_record_frame_time(elapsed)` / `measured_fps()`

A **moving average** over the last `FPS_WINDOW` (20) frames.

**Why a moving average:** one very slow frame (another program grabbing the CPU) would make an
instant rate jump from 7 to 2 and back, which looks like a bug. Averaging shows the real
throughput.

> Example: 20 frames in 2.8 s → `20 / 2.8 ≈ 7.1 fps`.

### `_build_snapshot(...)` — the contract

Assembles the exact dict the browser receives:

```python
{
  "ts": 31.5, "source": "crowded.mp4", "fps": 7.1,
  "total_people": 7, "peak_people": 9,
  "zones": [{
      "name": "Main Zone", "count": 7, "capacity": 4,
      "fill": 1.75, "status": "OVER", "over_for": 3.2,
      "avg_dwell": 12.0, "max_dwell": 24.0, "avg_speed": 18.4
  }],
  "alerts_active": 1, "new_alert": null
}
```

**Why every number is cast to `int`/`float`:** numpy scalars are not JSON-serialisable, and
FastAPI would raise when `np.int64(7)` reached the encoder.

**Why `fill` is computed here and not in the browser:** it is computed next to `status`, so the
gauge ring and the status chip can never disagree.

### `render(boxes, zones_on, heat)` — the video path

Builds **one JPEG** from the newest frame, drawing only what the query flags ask for.

**Why flags:** `/video` is polled with query parameters, so the browser toggles overlays without
restarting the engine or the stream.

**Why a copy first:** every drawing call modifies in place, and the frame inside `SharedState`
must stay clean for the next request and for the evidence photos.

**Before the first frame** it sends a black "starting engine..." image, so the browser never
shows a broken-image icon.

**Heat blending** happens only where the mask is true: `blended × (1 − alpha) + tint × alpha`.
Outside the mask the frame is untouched, so people and zone borders stay sharp.

### `_zones_for_render(snapshot)`

Rebuilds `Zone` objects and counts from the current snapshot, using a **per-clip cache**.

**Why a cache:** `/video` renders up to 15 frames a second; re-parsing `zones.json` for each one
is 15 file reads a second for data that only changes when zones are edited.

**Why keyed by clip:** switching source must never reuse another camera's polygon.

**Why try/except around `load_zones`:** if `zones.json` is being hand-edited while the server
runs, a malformed file must not break the video stream — the overlay just disappears for a
moment.

### `_encode(canvas)`

One `cv2.imencode(".jpg", ...)` at `JPEG_QUALITY`. Example: a 640×360 frame at quality 80 is
typically 25–60 KB.

---

## 4.7 `app/main.py` — the web layer

**Why it is thin:** all the thinking already lives in `engine.py`, `db.py` and `zones.py`. This
file only translates HTTP requests into calls on those modules and serialises the answers.
Keeping it thin means a web bug is a web bug, never a detection bug.

**Why the engine is a module-level singleton started in `lifespan`:** the model must load
**once**, not once per request, and the background thread must outlive individual requests but
die with the application. FastAPI's `lifespan` is exactly that scope.

### Routes

| Route | Returns | Why it exists |
| --- | --- | --- |
| `GET /` | `static/index.html` | the dashboard |
| `GET /video?boxes=1&zones=1&heat=0` | MJPEG stream | live annotated video |
| `WS /ws` | snapshot JSON every 0.5 s | live numbers |
| `GET /api/zones?source=` | zone polygons + capacities | so the browser can draw gauges before data arrives |
| `GET /api/alerts?limit=` | newest alerts | the alert feed |
| `GET /api/history?minutes=` | headcount samples, oldest first | the line chart |
| `GET /api/sources` | clip names | the source picker |
| `POST /api/source` | `{"ok": true, "source": ...}` | switch clips |

### `GET /video` — why MJPEG

`multipart/x-mixed-replace` lets a browser display a live stream **inside a plain `<img>` tag**
and keep replacing the picture. No JavaScript, no WebSocket, no video codec, no WebRTC
signalling. It is the simplest thing that works and it is easy to explain.

**Why a normal (sync) generator:** each frame is a small blocking CPU job (drawing + JPEG
encoding). Starlette runs a sync generator in its threadpool, so it does **not** block the event
loop that serves `/ws` and the API. An async generator would block that loop.

**Why `time.sleep(delay)`:** there is no point sending faster than `MJPEG_MAX_FPS` (15); without
the cap the stream would push the CPU to 100% for no visible gain.

**Why `while request.client is not None` and a `finally`:** when the browser closes the tab,
Starlette closes the generator, the `finally` runs, and that client's CPU share is freed.

### `WS /ws`

A steady 2-per-second beat rather than sending only on change.

**Why:** the dashboard also needs to know that *nothing* changed, so it can show "live" state and
a last-update time. A steady beat is simpler than diffing, and the payload is about 500 bytes.

**Why catch `WebSocketDisconnect`:** a closed tab raises it, and that is normal, not an error.
Without the catch, every tab close would print a traceback.

### `POST /api/source`

Validates the name against `list_clips()` and returns **400** for an unknown name, not 404.

**Why 400:** the request is malformed (it names something that is not a valid source), not a
missing page. 400 tells the client "fix your body".

> Example: `{"name": "mid.mp4"}` → 200. `{"name": "../../zones.json"}` → 400.

---

## 4.8 `static/index.html` — the dashboard markup

Plain HTML with Tailwind utility classes. No build step, no framework. Seven regions, top to
bottom:

1. **Sticky top bar** — logo, title, source picker (filled from `/api/sources`), LIVE pill
   (reports the **WebSocket** state, not the engine's), FPS, clock.
2. **Inline error bar** — one line, only when a fetch fails or the socket drops.
3. **Congestion banner** — visible only while `alerts_active > 0`.
4. **KPI row** — 2×2 on phones, 4 across from 1024 px:
   *People now* · *Peak (session)* · *Average dwell* · *Processing FPS*.
5. **Main grid** — left 8/12: video card + headcount chart. Right 4/12: zone gauges + alert log.
6. **Footer** — live status and the credit line.
7. **Toast + evidence `<dialog>`** — a new alert announces itself; clicking an alert opens the
   saved photo.

**Why a `<dialog>` for evidence:** the browser gives focus trapping, Escape-to-close and an
inert backdrop for free, which is exactly the accessibility behaviour a hand-rolled modal would
get wrong.

**Why the KPI tooltips are pure CSS** (`ĸ.icon-badge[data-tip]::after`): no JavaScript, no
library, and they open **downward** so they clear the sticky header.

---

## 4.9 `static/app.js` — the browser logic

About 1,740 lines, organised in numbered sections. You do not need every line; you need the
**seven jobs**.

| Section | Job |
| --- | --- |
| 1. Helpers | `escapeHtml`, `statusClass`, `formatDwell`, **`formatSpeed`**, `videoLabel`, `clockTime` |
| 2. Fetching | `getJson`, `showError`, `clearError` |
| 3. KPIs | `animateKpi`, `renderKpis` |
| 4. Gauges | `gaugeMarkup`, `deriveStatus`, `renderGauges` |
| 5. Alerts | `normaliseAlert`, `alertRowMarkup`, `renderAlerts`, `prependAlert` |
| 6. Chart | `createChart`, `pushChartData`, `appendChartPoint`, `prefillChart`, `rebuildChart` |
| 7. Live wiring | `connectSocket`, `scheduleReconnect`, `update`, `videoUrl`, `bindToggle` |
| 8. Actions | `showToast`, `openEvidence`, `changeSource`, `loadInitialData`, `boot` |

### The functions most likely to be asked about

**`update(snapshot)`** — the single entry point for live data. It calls `renderKpis`,
`renderGauges`, `pushChartData`, `renderBanner`, `reconcileActiveAlerts` and, if
`snapshot.new_alert` is set, `prependAlert` + `showToast`.

**`gaugeMarkup(latest)`** — builds **one SVG ring per zone**. The ring is a `<circle>` with
`stroke-dasharray` equal to the circumference and `stroke-dashoffset` set to
`circumference × (1 − fill)`. Animating `stroke-dashoffset` via CSS gives a smooth sweep.

> Example: radius 52 → circumference `2π×52 ≈ 326.7`. At 75% full, offset = `326.7 × 0.25 ≈ 81.7`,
> so 245 px of the ring is drawn.

**Why the fill is clamped to [0, 1]:** an over-capacity zone cannot fill more than a full ring.
Without the clamp the offset goes negative and the arc wraps around, which looks like an *empty*
ring — the opposite of the truth.

**Why the snapshot's own `fill` is preferred:** it is computed next to `status` on the server, so
the ring and the chip can never disagree. `count / capacity` is only the first-half-second
fallback.

**`deriveStatus(count, capacity)`** — mirrors `status_for` in Python, for the half second before
the first snapshot arrives. The `0.8` is repeated on purpose and the comment says so.

**`formatSpeed(value)`** — `18.4 → "18 px/s"`, `0 → "—"`. The em dash matters: a person seen once
has no speed yet, and showing `0 px/s` would claim they are frozen.

**`connectSocket()` / `scheduleReconnect()`** — opens the WebSocket, and on any close retries
with a backoff instead of giving up. The LIVE pill reflects this state, so the operator knows
whether the numbers are fresh.

**`reconcileActiveAlerts(latest)`** — the dashboard's own safety net. The DB can hold an alert
row with `ended_at IS NULL` from an earlier session; if `over_for` is 0 for a zone, the alert is
not really active, so the UI does not show it as live.

**`prefillChart(rows)` vs `appendChartPoint(...)`** — the chart is seeded once from
`/api/history`, then extended live. Seeding avoids losing the history every time the page
reloads.

---

## 4.10 `static/style.css` — the theme

About 1,410 lines of CSS on top of Tailwind. What is actually worth explaining:

- **Design tokens** — all colours, radii, font sizes and shadows are CSS custom properties
  (`--bg`, `--panel`, `--text`, `--muted`, `--ok`, `--warn`, `--crit`). One place to change the
  whole theme.
- **`.glass`** — the card surface: translucent background, 1 px hairline border, soft shadow,
  `backdrop-filter` blur. It is what makes the dashboard read as a "command centre" rather than
  a spreadsheet.
- **`.tnum`** — `font-variant-numeric: tabular-nums`. Without it, changing `7` to `11` shifts the
  layout sideways; with it, digits have equal width and numbers stay put.
- **`.status-chip`** — the OK / NEAR / OVER pill, with a matching outline icon so the meaning is
  not carried by colour alone (important for colour-blind users).
- **`.gauge-*`** — the SVG ring, the number, the `/ capacity` label, the dwell line and the new
  speed line.
- **Reduced motion** — a `prefers-reduced-motion` block turns off the non-essential transitions.
- **Vendored assets** — Tailwind and Chart.js are checked into `static/vendor/` so the demo runs
  with the network cable unplugged. There is no CDN call and no build step.

**Contrast was measured, not guessed:** the muted text colour is `#8FA3BF`, which is **7.03:1**
against the panel background (WCAG AA needs 4.5:1 for body text), and the footer credit was
raised to **5.76:1**.

---

## 4.11 `zones.json` — the operator's configuration

```json
{
  "crowded.mp4": [
    {
      "name": "Main Zone",
      "capacity": 4,
      "polygon": [[284, 232], [300, 274], [352, 309], [346, 359], [488, 359], [467, 329], [404, 334], [330, 235]]
    }
  ],
  "mid.mp4":    [ ... capacity 5 ... ],
  "normal.mp4": [ ... capacity 4 ... ]
}
```

**Why JSON and not code:** zones are *data*, not logic. An operator can change a polygon or a
capacity without touching Python, and the file is readable on a projector.

**Why per clip:** a different camera angle needs a different polygon. Coordinates are in the
**resized** 640-wide frame, because that is the frame the detector sees, so foot points and
polygons use the same units.

**Why capacities differ (4 / 5 / 4):** each clip has a different crowd density. The capacity is
chosen so that `crowded.mp4` genuinely goes over (producing an alert to demonstrate) while
`normal.mp4` stays comfortably under (proving no false positive).

---

## 4.12 `tests/test_pipeline.py` — 20 tests in one file

**Why one file instead of six:** the project is graded on being explainable. One file that reads
top to bottom **in the same order as the data flows** — person → zone → analytics → database →
shared state — is far easier to walk a panel through than six files they must open one by one.

The classes, in that order:

| Class | Proves |
| --- | --- |
| `TestFootPoint` | bottom-centre maths |
| `TestResize` | aspect ratio kept; zero width rejected |
| `TestZones` | inside/outside lookup; 7/8/10/11 → OK/NEAR/NEAR/OVER |
| `TestDwell` | 3.4 s example; departed person forgotten |
| `TestSpeed` | first sighting has no speed; 40 px in 2 s = 20 px/s |
| `TestDebouncer` | 1 s spike does nothing; 4 s fires once; clears after 5 s under |
| `TestHeatmap` | empty map draws nothing; a point heats its own pixel |
| `TestDatabase` | alert round-trip; peak never lowers; history in order |
| `TestSharedState` | empty snapshot is well-formed; `get` returns a copy |
| `TestClips` | allow-list contains no path separators |

Run them with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Two tests are worth memorising because they are the behaviour a panel will ask about:

- **`test_sustained_over_capacity_triggers_once`** — 4 s over capacity produces exactly one
  `TRIGGERED`. This is the anti-spam proof.
- **`test_peak_never_lowers`** — writing a *lower* count leaves the stored peak unchanged. This
  is the "evidence is preserved" proof.

---

# Part 5 — The numbers in the app

Panel members like concrete arithmetic. These are the ones that actually appear.

### Counts and fill

- Zone capacity 4, 7 people inside → `fill = 7 / 4 = 1.75`, status **OVER**.
- The gauge ring is clamped to `1.0`, so it draws a **full** ring; the OVER chip communicates
  the excess.
- 3 people in a capacity-4 zone → `fill = 0.75`, and `0.75 < 0.8` → **OK**.
- 4 people in a capacity-4 zone → `fill = 1.0`, `4 >= 0.8×4` → **NEAR**, not OVER.

### Dwell

- ID 7 enters at video 9.0 s; now 12.4 s → dwell `3.4 s`.
- Ten people studied: nine at 2 s, one at 60 s → **average** `(9×2 + 60)/10 = 7.8 s`,
  **max** `60 s`. The average hides the problem; the max reveals it.

### Speed

- Foot (100,200) at 1.0 s → foot (140,200) at 3.0 s.
- Distance `40 px`, elapsed `2 s` → **20 px/s**.
- Diagonal case: (0,0) → (30,40) is `sqrt(900+1600) = 50 px`.

### Heat decay

- `1.0 × 0.995^1 = 0.995`
- `1.0 × 0.995^10 ≈ 0.951`
- `1.0 × 0.995^100 ≈ 0.61`
- After ~460 frames (≈28 s at 16 fps) the heat is down to about 10% of where it started.

### Alert timing

- `ON_DELAY 3 s`: over at 0, 1, 2, 3 → fires at the 3 s call. Over again at 4 s → silent,
  because the alert is already active.
- `OFF_DELAY 5 s`: back under at 4 s → clears at 9 s.

### Processing rate

- Measured on this laptop: **16.6 / 16.1 / 15.9 fps** for crowded / mid / normal.
- Required to keep up with `STRIDE 2`: **14.98 / 14.98 / 12.50 fps** — so all three clips are
  comfortably real-time-equivalent.
- p95 frame time **86.3 / 79.3 / 83.6 ms**.
- `detect+track` is **≈78–79%** of each frame — the single dominant cost.
- 20 frames in 2.8 s → moving-average FPS `20 / 2.8 ≈ 7.1` (this is a slower moment; the
  figure above is the sustained rate).

### The severity thresholds in one line

`OK` under 80% · `NEAR` at 80–100% · `OVER` above 100%.

---

# Part 6 — Design decisions and why they are defensible

Prepare one sentence each. These are the questions that separate "I copied a tutorial" from
"I built this".

### 1. Why split the engine into a background thread?

Because vision is slow (~60–110 ms/frame) and the web must be instant. One thread does the slow
work and publishes; requests read the last published result. The dashboard never freezes while
the model thinks.

### 2. Why YOLOv8 **nano** and not a bigger model?

The machine is a 4-core laptop with **no GPU**. Nano is the smallest YOLOv8 and still detects
people well at 640 px. A larger model would be more accurate on distant people but would fall
below real-time. I measured the trade-off honestly: comparing against a much larger model shows
nano misses some distant/small people, and that is a documented limitation rather than a bug.

### 3. Why ByteTrack?

It ships **inside ultralytics** — no extra dependency — and it is designed for exactly this:
stable IDs through brief occlusion at video rates. It also keeps working when a detector misses
a frame, which matters because `STRIDE 2` already skips frames.

### 4. Why every 2nd frame (`STRIDE 2`)?

It roughly doubles throughput. At 29.97 fps source, analysing every 2nd frame still gives ~15
analyses per second, which is far more than the 2-per-second the dashboard needs and enough for
smooth box motion. The dwell and alert logic use **time**, not frame counts, so skipping frames
does not break them.

### 5. Why pixels-per-second for speed?

Converting to km/h needs camera calibration (floor plane, distance, perspective). Without it any
"km/h" number would be invented. Pixels per second is honest and still lets you compare zones
within one clip — which is the operational question ("is this zone moving or stuck?").

### 6. Why does the alert wait 3 seconds?

Because the count flickers by ±1 constantly. Alerting on the raw signal would produce dozens of
alerts for one crowd. 3 seconds of sustained over-capacity is long enough to ignore a detection
blip and short enough to still be useful.

### 7. Why 5 seconds to clear?

An alert must not flicker off the moment one person steps out. 5 s of sustained normal traffic
means the crowd really has dispersed.

### 8. Why is data stored in SQLite?

Zero setup, a single file, standard library, and it survives restarts. A demo that forgets its
history every time you close the terminal cannot show an alert log.

### 9. Why MJPEG instead of WebRTC?

WebRTC needs signalling, STUN/TURN and a codec pipeline — a lot of machinery to display a
640×360 stream on localhost. MJPEG renders inside a plain `<img>` tag with no JavaScript and no
extra dependency. The trade-off (higher bandwidth than H.264) does not matter on loopback.

### 10. Why is the front end plain HTML instead of React?

The brief asks for no build step. Plain HTML + Tailwind + Chart.js loads instantly, has no
toolchain to break before a demo, and every line is readable in the browser. The whole UI is
three files.

### 11. Why are zones in a JSON file?

Zones are configuration, not code. An operator can redraw a polygon or change a capacity without
touching Python — and there is no magic number hiding inside a function.

### 12. What happens if the model misses a person?

Two safeguards. ByteTrack keeps a track alive for `TRACK_GRACE` (2 s), so a one-frame miss does
not reset the dwell clock. And the alert **debouncer** requires 3 s of sustained over-capacity,
so a single missed detection cannot fire an alert.

### 13. What are the real limitations?

Say these plainly — honesty scores well:

- **nano misses small/distant people**, so counts are a lower bound in very wide shots.
- **Pixels, not metres** — no calibration, so speed is not a physical unit.
- **One zone per clip** in the demo; the code supports many, the demo keeps it simple.
- **No identity/re-identification** — a track ID is not a person's identity, and IDs reset
  between clips.
- **CPU-only**, so sustained throughput is ~16 fps, not 30.
- **Zone polygons are static** — a moving camera would need re-drawing.
- **The heatmap is a footprint density map**, not a true spatial density (people per m²), because
  we have no calibration.

### 14. Why does the dashboard show "NEAR" at 80%?

So an operator gets a warning *before* the area is actually full. A gauge that is silent until
100% gives no time to react.

---

# Part 7 — The PDF requirements, mapped

Track A, "Crowd density and bottleneck analytics" (slide 5):

| Requirement | Where | How |
| --- | --- | --- |
| **01 People and occupancy** — detect and track people, count within configured zones | `vision.py`, `zones.py` | YOLOv8n + ByteTrack → `Person` with `track_id`; `count_by_zone` groups by foot point |
| **02 Density and flow** — density heatmaps and estimated movement velocity | `analytics.py` | `HeatmapAccumulator`; `SpeedTracker` (px/s) |
| **03 Dwell and thresholds** — measure dwell, alert when a zone exceeds capacity | `analytics.py`, `engine.py` | `DwellTracker`; `AlertDebouncer` + `status_for` |
| **Live video** — density heatmaps and bounding boxes | `engine.render` | boxes, foot dots, zone polygons, masked heat overlay |
| **Capacity and headcount** — zone gauges and headcount time-series charts | `index.html`, `app.js`, `db.py` | SVG ring gauges; Chart.js line chart fed from `headcount` |
| **Congestion warnings** — visible banners when thresholds trigger | `index.html`, `app.js` | banner driven by `alerts_active`; toast on `new_alert` |

Architecture (slide 16) — the four layers are exactly what Part 2 shows:
image/video input → vision and rules → backend and storage → web dashboard, with
"REST for history, WebSockets for events" and MJPEG for video.

Front-end experience (slide 17): live visual feedback (counters, banner, toast), operator
context (chart, gauges, severity chips, evidence snapshots), responsive controls (overlay
toggles, fullscreen, source picker).

Demo data and validation (slide 19): three clips at three different densities, in
`demo_videos/`, with the expected results documented in `demo_videos/expected_results.md`.
The clips are openly licensed stock footage from Pexels rather than phone recordings; each one
is a single continuous stretch, and `demo_videos/SOURCES.csv` records the original URL, author
and licence for all three. Be ready to say this plainly - it is a defensible choice, but the
panel should hear it from you rather than discover it.

Submission checklist (slide 22): GitHub repo with frontend + backend + vision engine, README,
architecture diagram, demo dataset with expected results, and a live walkthrough.

Evaluation rubric (slide 20) - and how this maps:

| Criterion | Weight | How this project targets it |
| --- | --- | --- |
| **Front-end UI/UX richness** | **60%** | Dark command-centre theme, animated KPIs, SVG ring gauges, Chart.js line chart with a capacity line, congestion banner, toast, evidence modal, full keyboard/ARIA support, responsive from 360 px |
| Vision pipeline and accuracy | 20% | YOLOv8n + ByteTrack, tuned `conf`, `STRIDE`, honest measured accuracy + documented limitations |
| Custom demo and realism | 10% | Three clips at three densities (Pexels stock footage, credited in SOURCES.csv), documented expected results, evidence photos |
| System architecture and scope | 10% | Four clean layers, config module, single-file DB module, thin web layer, 20 tests |

---

# Part 8 — Likely questions and short answers

**"Walk me through what happens when I open the page."**
The browser loads `index.html`, calls `/api/sources`, `/api/zones`, `/api/history` and
`/api/alerts`, then opens `/ws` and sets the `<img>` source to `/video`. Meanwhile the engine
thread is already looping over the clip. Every 0.5 s the WebSocket pushes a snapshot; the JS
re-renders the KPIs, gauges and chart. The `<img>` receives a new JPEG up to 15 times a second.

**"Where does the number 7 on the KPI tile come from?"**
`count_by_zone` counted feet inside zones in the newest analysed frame; `_build_snapshot` summed
those counts into `total_people`; `SharedState` published it; `/ws` sent it; `renderKpis` wrote it
into `[data-kpi="people"]`.

**"Why does a zone show OVER but the ring is full, not overflowing?"**
`fill` is `count / capacity` (e.g. `7/4 = 1.75`), and the client clamps it to 1.0 so the SVG
dash-offset never goes negative and wrap the arc. The OVER chip carries the excess information.

**"Why is the alert saved twice — once in memory and once in SQLite?"**
The DB is the durable record for the **history**. The in-memory `active_alerts` dict is the
**live** state so the engine knows which row to close, and `peak_counts` avoids a DB write on
every frame for a value that rarely changes.

**"What if two zones overlap?"**
`zone_of` returns the **first** matching zone in `zones.json` order. First match wins, and the
most important zone is listed first. A person is counted once, never twice.

**"What if the video file is missing at startup?"**
`_play_clip` raises `RuntimeError("Cannot open clip")`, `run()` catches it, prints the reason and
retries after 1 s. The web server stays up and the dashboard shows the error bar rather than a
crash.

**"How do you know it does not produce false alerts?"**
`normal.mp4` — the low-density clip — runs a full loop and produces **0** alerts while
`crowded.mp4` produces exactly the expected alert. That is the false-positive test, and it is
part of the demo evidence.

**"Did you record the demo footage yourself?"**
No — say it directly. The three clips are openly licensed stock footage from Pexels, and
`demo_videos/SOURCES.csv` records the original URL, author and licence for each one. What *is*
custom is everything around them: the choice of three density levels, the zone polygons drawn for
each camera angle, the capacities (4 / 5 / 4) tuned so one clip alerts and two do not, and the
measured expected-results table. If the panel pushes on it, the honest answer is that recording
original crowd footage was not possible in the time available, and using credited stock footage
let the effort go into the pipeline and dashboard instead — which is where 80% of the marks sit.

**"How fast is it, and can you prove it?"**
~16 fps sustained on a 4-core laptop with no GPU, measured as a moving average over 20 frames.
The dashboard displays the live figure in the "Processing FPS" tile, and `detect+track` accounts
for ~78–79% of each frame.

**"What would you do with more time?"**
Add a calibration step so speed can be reported in metres per second, add a "save this zone"
editor in the UI, and cache detection results per frame so the same clip does not re-run the
model.

---

# Appendix — Run it before the interview

```powershell
cd C:\Users\akshaya\Downloads\crowd-analytics
.\start.bat
```

Or manually:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open <http://127.0.0.1:8000>.

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: `Ran 20 tests ... OK`.

### A 3-minute demo script

1. **Open the page on `crowded.mp4`.** Point at the video: "boxes are detections, the coloured
   polygon is the monitored zone with its live count, and the heat colours show where people
   keep standing."
2. **Point at the four KPIs.** "People now, peak this session, average dwell, and actual
   processing FPS on this machine."
3. **Wait for the alert.** The banner appears and a toast announces it. "That fired because the
   zone was over capacity for 3 continuous seconds — a single frame would not have triggered it."
4. **Show the zone gauge.** "The ring is the fill ratio; the chip says OVER; below it is average
   dwell and average movement speed."
5. **Click the alert.** The evidence photo opens — the frame that caused it, with boxes and
   zones drawn in.
6. **Switch to `normal.mp4`.** "Same pipeline, low density — no alert, which is the
   false-positive check."
7. **End on the chart.** "This is the headcount over time, with the capacity line drawn across
   it."
