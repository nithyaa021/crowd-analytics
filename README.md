# Crowd Density and Bottleneck Analytics

A live dashboard that watches a video feed, tracks people inside configurable zones, and warns an
operator the moment an area goes over its safe capacity.

Built for **Cogno Valley — Track A** with Python, YOLOv8 nano + ByteTrack, OpenCV, FastAPI and
SQLite, on a CPU-only Windows laptop. Front end is plain HTML + Tailwind + Chart.js with no build
step.

![status](https://img.shields.io/badge/status-working-brightgreen)
![python](https://img.shields.io/badge/python-3.10--3.12-blue)
![tests](https://img.shields.io/badge/tests-20%20passing-brightgreen)

---

## What it does

Three questions, answered continuously:

1. **How many people are in each zone right now?** — YOLOv8 nano detects people, ByteTrack gives
   each a stable ID, and each person's foot point is tested against the zone polygon.
2. **How long are they staying, and are they moving?** — average and longest dwell per zone, plus
   average movement speed in pixels per second.
3. **Is any zone over capacity?** — a debounced rule fires an alert only after a zone has been
   over capacity for 3 continuous seconds, saves an evidence photo, and shows a banner.

The dashboard shows the annotated video (boxes, zone polygons, density heatmap), four KPI tiles,
SVG ring gauges per zone, a headcount time series, and an alert log with clickable evidence
photos.

---

## Architecture

Four layers, one direction of data flow. The slow vision work and the fast web responses are
separated by a single shared object.

```
LAYER 1 — INPUT
  demo_videos/*.mp4  ->  OpenCV VideoCapture  ->  640-wide BGR frame
                              |
LAYER 2 — VISION AND RULES                       app/vision.py, zones.py, analytics.py
  YOLOv8 nano -> person boxes
  ByteTrack   -> stable track IDs
  zones.json  -> which zone is each foot point in
  analytics   -> dwell, speed, heatmap, alert debounce
                              |
                     snapshot dict + drawn frame
                              v
LAYER 3 — BACKEND AND STORAGE                   app/engine.py, db.py, main.py
  Engine thread -> runs forever, publishes SharedState
  SQLite        -> alerts + headcount history
  FastAPI       -> REST for history, WebSocket for live numbers, MJPEG for video
                              |
                     HTTP + WebSocket on 127.0.0.1:8000
                              v
LAYER 4 — WEB DASHBOARD                         static/index.html, app.js, style.css
  Live video with boxes, zones and heatmap
  4 KPI tiles, zone gauges, headcount chart, alert log
  Congestion banner, toast, evidence modal
```

**The key idea:** reading a frame and running the model takes 60–110 ms, but a browser asking for
numbers must be answered in microseconds. So two threads exist — the **engine** does the slow work
and publishes its latest result, and the **web** thread only reads that result. They meet at
`SharedState`, guarded by one lock. No request ever waits for the model.

---

## Quick start

Requires **Python 3.10–3.12** (3.13 is not supported by the pinned dependencies).

```powershell
cd C:\Users\akshaya\Downloads\crowd-analytics

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\start.bat
```

`start.bat` activates the virtual environment, opens <http://127.0.0.1:8000> in your browser, and
starts the server. Or start it by hand:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The first run downloads `yolov8n.pt` (about 6 MB) if it is not already present. Everything after
that is offline.

### Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: `Ran 20 tests ... OK`.

---

## The demo clips

Three self-recorded clips at three densities, in `demo_videos/`. Expected results are documented
in [`demo_videos/expected_results.md`](demo_videos/expected_results.md).

| Clip | People (median / max) | Capacity | Expected alert |
| --- | --- | --- | --- |
| `normal.mp4` | 2 / 4 | 4 | none — the false-positive check |
| `mid.mp4` | 5 / 12 | 5 | none — spikes are too short to sustain 3 s |
| `crowded.mp4` | 8 / 15 | 4 | one alert at about 31.5 s, peak 8/4 |

Switch clips from the picker in the top bar; the engine rebuilds all tracking state and starts the
new clip from the beginning.

---

## Project layout

```
crowd-analytics/
├── app/
│   ├── config.py        every tunable number, in one file
│   ├── vision.py        YOLO + ByteTrack; returns Person objects
│   ├── zones.py         zone polygons, capacity, the OK/NEAR/OVER rule
│   ├── analytics.py     dwell time, speed, heatmap, alert debounce
│   ├── db.py            SQLite: alerts table + headcount table
│   ├── engine.py        the background video loop and SharedState
│   └── main.py          FastAPI routes (the whole web layer)
├── static/
│   ├── index.html       dashboard markup
│   ├── app.js           fetches data, draws gauges, chart and alerts
│   ├── style.css        dark command-centre theme
│   └── vendor/          Tailwind + Chart.js, so the demo runs offline
├── tests/
│   └── test_pipeline.py 20 tests, ordered person -> zone -> analytics -> db
├── demo_videos/         three clips + expected_results.md
├── zones.json           zone polygons and capacities, per clip
├── CODE_GUIDE.md        the full code walkthrough, file by file
├── requirements.txt     pinned dependencies
└── start.bat            double-click launcher
```

---

## API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | the dashboard |
| `GET` | `/video?boxes=1&zones=1&heat=0` | MJPEG stream, overlays toggled by query flags |
| `WS` | `/ws` | live snapshot JSON, twice per second |
| `GET` | `/api/sources` | clip names available in `demo_videos/` |
| `POST` | `/api/source` | switch clip, body `{"name": "mid.mp4"}` |
| `GET` | `/api/zones?source=` | zone polygons and capacities for a clip |
| `GET` | `/api/alerts?limit=` | newest alerts, including the evidence photo URL |
| `GET` | `/api/history?minutes=` | headcount samples, oldest first |

Example snapshot pushed over the WebSocket:

```json
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

---

## Configuration

All tunable numbers live in [`app/config.py`](app/config.py) — there are no magic numbers elsewhere.

| Setting | Value | Effect |
| --- | --- | --- |
| `CONF` | `0.35` | minimum confidence for a detection to count as a person |
| `STRIDE` | `2` | analyse every 2nd frame (roughly doubles throughput) |
| `ON_DELAY` | `3.0` s | how long over capacity before an alert fires |
| `OFF_DELAY` | `5.0` s | how long back to normal before it clears |
| `NEAR_RATIO` | `0.8` | fraction of capacity that shows amber NEAR |
| `TRACK_GRACE` | `2.0` s | how long a lost track is remembered |
| `HEAT_DECAY` | `0.995` | how fast old heatmap heat fades |

Zones live in [`zones.json`](zones.json), one entry per clip, because each camera angle needs its
own polygon. Coordinates are in the 640-wide resized frame, which is the frame the detector sees.

---

## Measured performance

On the target laptop — 11th Gen Intel i3-1125G4, 4 physical cores, no GPU:

- **~16 fps** sustained processing (crowded / mid / normal: 16.6 / 16.1 / 15.9 fps)
- `detect + track` is about **78–79%** of each frame's cost
- p95 frame time **79–86 ms**
- To keep up with `STRIDE 2` at 29.97 fps source, 14.98 fps is needed — so all three clips run
  faster than real-time-equivalent

---

## Limitations, stated plainly

- **Pixel speed, not km/h.** Converting pixels to metres needs camera calibration (floor plane,
  distance, perspective) which this project does not have. Pixels per second is honest and still
  lets you compare zones within one clip.
- **Nano misses small or distant people**, so counts are a lower bound in very wide shots. A larger
  model is more accurate but would not hold real time on this CPU.
- **Zone polygons are static**, so a moving camera would need them re-drawn.
- **Track IDs are not identities.** No re-identification; IDs reset when the clip changes.
- **One zone per clip** in the demo. The code supports many; the demo keeps it simple.
- **The heatmap is a foot-density map**, not a true people-per-square-metre density, again because
  there is no calibration.

---

## Further reading

[`CODE_GUIDE.md`](CODE_GUIDE.md) is a full walkthrough: the architecture, the frame-by-frame data
flow, every file and function, the worked arithmetic behind each number, the design decisions and
their justifications, and the likely interview questions with short answers.

---

## Licence

All dependencies are open source (AGPL-3.0 for Ultralytics YOLOv8, Apache-2.0 for FastAPI,
MIT for the rest). Demo clips were recorded for this project.
