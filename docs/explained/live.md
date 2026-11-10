# Step P7 - Live data: one number from the engine to the screen (explained for a beginner)

This note explains step P7 in plain English and then follows **one single value - the people
count - from the moment the engine measures it to the moment it appears on screen**. Read that
trail once, and you can explain the whole dashboard.

Nothing in the Python backend changed. P7 is entirely `static/app.js`, plus small additions to
`static/index.html` (error bar, toast, modal) and `static/style.css` (their styles).

---

## 1. What changed, in six sentences

1. The P6 `SAMPLE` object is **gone**. Every number now comes from the server.
2. A **WebSocket client** connects to `/ws`, and if the connection drops it retries with
   exponential backoff: 1 s, 2 s, 4 s, 8 s, then 10 s forever.
3. The **LIVE pill** says `Connected` or `Reconnecting`, so an operator always knows whether the
   numbers are still moving.
4. On first load, four **fetches** fill the parts that are not in a snapshot: zone list, alert
   history, chart history, source list.
5. **New alerts** are prepended to the log, flashed, and announced in a toast.
6. Every fetch is wrapped in `try/catch` and reports into a single **inline error bar**, so the
   page is never blank and never uses `alert()`.

---

## 2. The trail of one number: `total_people`

This is the most important section. Nine steps, each one a real line of code.

### Step 1 - YOLO counts people in a frame

`app/engine.py`, inside the video loop, calls the detector and gets a list of `Person` objects.
For each person the **foot point** (the bottom-centre of the box) is used, because that is where
the person touches the floor.

```
Frame 00031: 6 boxes -> 6 foot points
```

### Step 2 - Foot points are assigned to zones

`count_by_zone(zones, people)` returns a dict of lists:

```
{"Main Zone": [p1, p2, p3, p4, p5]}
```

### Step 3 - The counts become a snapshot dict

`Engine._build_snapshot` assembles the message. Every value is cast to `int` or `float` because a
numpy integer is not JSON-serialisable:

```python
"total_people": int(sum(counts.values())),     # 5
```

The full message also carries `ts`, `source`, `fps`, `peak_people`, `zones[]`, `alerts_active`
and `new_alert`.

### Step 4 - The snapshot goes into `SharedState`

One lock, one write. The web server never waits for YOLO; it only ever copies the newest result.

```
snapshot = {"ts": 31.5, "total_people": 5, ..., "zones": [{..., "count": 5, ...}]}
```

### Step 5 - `/ws` pushes it to the browser

`app/main.py` (`websocket_endpoint`) loops every `WS_INTERVAL` = **0.5 s**:

```python
await websocket.send_json(snapshot)
await asyncio.sleep(0.5)
```

Two messages per second, to every connected tab.

### Step 6 - The browser receives text and parses it

`static/app.js`:

```js
socket.addEventListener("message", (event) => {
  update(JSON.parse(event.data));
});
```

`event.data` is a **string**. `JSON.parse` turns it back into an object whose `total_people` is
the number `5`.

### Step 7 - `update(snapshot)` hands it to the KPI renderer

```js
renderKpis(snapshot);   // reads snapshot.total_people
```

### Step 8 - `renderKpis` computes what to show

```js
const total = Number(snapshot.total_people) || 0;   // 5
animateKpi("people", total);
```

### Step 9 - `animateKpi` writes pixels

```js
node.innerHTML = escapeHtml(text);   // the digit "5" inside <div data-kpi="people">
```

**That is the whole journey.** The number was measured by a neural network, passed through a
Python dict, JSON, a WebSocket frame, `JSON.parse`, and one `innerHTML` write, and it is now the
`5` in the "People now" card.

### The same trail for the other panels

| Panel | Field in the snapshot | Function |
| --- | --- | --- |
| People now | `total_people` | `renderKpis` -> `animateKpi("people")` |
| Peak | `peak_people` | `animateKpi("peak")` |
| Average dwell | `zones[].avg_dwell` (the largest) | `animateKpi("dwell")` |
| Processing FPS | `fps` | `animateKpi("fps")` |
| Gauge ring | `zones[].fill` | `gaugeMarkup` |
| Gauge colour / chip | `zones[].status` | `gaugeMarkup` |
| Banner | `alerts_active`, `zones[].over_for` | `renderBanner` |
| New alert | `new_alert` | `prependAlert` + `showToast` |
| Chart point | `ts`, `total_people`, `zones[].count` | `appendChartPoint` |

---

## 3. The count-up animation (and the bug hiding inside it)

A raw KPI write jumps `8 -> 12 -> 9`. The eye cannot tell a rise from a fall. So each number
animates over **300 ms**:

```
from 8 to 12, at 50% of the way:
  linear   = 8 + (12-8) * 0.5  = 10.0
  eased    = 8 + (12-8) * (1 - (1-0.5)^3) = 8 + 4 * 0.875 = 11.5
```

`easeOutCubic` moves fast first and settles, which reads as "arriving" rather than "crawling".

Points move; the count is rounded for display, so the visible sequence is `8, 10, 11, 12`.

### The bug this section exists to explain

The animation is driven by `requestAnimationFrame`. **Browsers stop firing it for a hidden tab.**
The first version had no fallback, so if you switched tabs during a 300 ms animation, the number
froze halfway - permanently showing `7.3 s` while the true value was `9.0 s`.

The fix is a **guaranteed landing**:

```js
const timer = setTimeout(() => { render(to); app.kpiAnim.delete(key); },
                         KPI_ANIM_MS + 60);
```

Whatever happens to the frames, the card shows the true value within 360 ms. The animation is a
nicety; the number is the product. I found this because the browser pane I tested in throttles
`requestAnimationFrame` when it is not focused, and the KPI cards sat at `0` while
`dataset.value` held `8.4`.

`prefers-reduced-motion` is also honoured: the count-up is skipped and the value is written once.

---

## 4. The ring gauge, driven by `fill`

The snapshot already contains the ratio, so the gauge uses it rather than recomputing:

```js
const rawFill = Number.isFinite(Number(live.fill)) ? Number(live.fill) : count / capacity;
const fraction = Math.min(Math.max(rawFill, 0), 1);       // clamp to [0, 1]
const offset = 326.73 * (1 - fraction);                   // C = 2 * pi * 52
```

Verified in the running page:

| Snapshot | `fill` | Clamped fraction | `stroke-dashoffset` | Ring shows |
| --- | --- | --- | --- | --- |
| 2 of 4 | 0.5 | 0.5 | **163.36** | half full |
| 4 of 4 | 1.0 | 1.0 | **0.00** | full, NEAR |
| 6 of 4 | 1.5 | 1.0 | **0.00** | full, OVER, red |

Without the `Math.min(..., 1)` clamp, `1.5` would give `offset = -163.36`, and a negative offset
wraps the dash around so the busiest zone renders as an almost **empty** ring. That single clamp
is the difference between "correct at a glance" and "lying".

Status drives colour and chip from one lookup:

```js
const STATUS_STROKE = { OK: "var(--ok)", NEAR: "var(--warn)", OVER: "var(--crit)" };
```

So the arc colour, the chip class and the `OVER` word can never disagree - they all read the same
`status` field that Python computed with `status_for`.

---

## 5. The chart

Three kinds of line, all fed from the same snapshot:

* **Total** - `total_people`, filled with a gradient, 2 px.
* **One line per zone** - `zones[i].count`, 1.5 px, colour from a fixed palette, so a zone keeps
  its colour all session.
* **Capacity** - a flat dashed line at the **largest zone capacity**, so "above the line" means
  "over capacity" for whichever zone is closest to it.

A point is added per message, labelled with **video time** (`00:31`), not wall time - so the
spike lines up with the frame you can see.

The window is capped at **120 points**:

```js
const overflow = app.chart.labels.length - CHART_MAX_POINTS;
if (overflow > 0) {
  app.chart.labels.splice(0, overflow);     // drop the oldest
  app.chart.total.splice(0, overflow);
  Object.values(app.chart.perZone).forEach((series) => series.splice(0, overflow));
}
```

Why 120: at two seconds per database row that is four minutes. Before the cap the array would grow
for the whole session and the tab would slowly get heavier. Verified in the running page: the
chart sat at exactly `120` labels and stopped growing.

`chart.update("none")` repaints **without** an animation, because a point arriving every 500 ms
would otherwise start an endless 300 ms ease that the next point outruns.

---

## 6. The banner

```js
if (Number(snapshot.alerts_active) > 0) {
  renderBanner(worstZone(zones) || zones.find((z) => z.status === "OVER") || null);
} else {
  renderBanner(null);
}
```

`worstZone` picks the over-capacity zone with the largest `over_for`:

```
zones: A over_for 4.2, B over_for 9.8  ->  banner names B
zones: none OVER                        ->  banner hidden
```

`over_for` comes straight from `AlertDebouncer.over_for`, which is `0.0` whenever the zone is not
currently over capacity. That property turned out to matter a lot - see section 9.

---

## 7. New alerts: prepend, flash, toast

When `snapshot.new_alert` is not null it looks like:

```json
{ "id": 24, "zone": "Main Zone", "keyframe": "/evidence/alert_24.jpg" }
```

Three things happen:

1. **Prepend** - one `<li>` is inserted at the top rather than re-rendering the list. A full
   re-render would reset the scroll position and flash every row at once.
2. **Flash** - the new row gets `.is-new`, which runs a 1.6 s expanding outline. An outline, not a
   background, because the background already encodes Active/Cleared.
3. **Toast** - a card slides into the bottom-right corner for 5 s:
   `Over capacity · Main Zone 5/4 people`.

Verified against the real code path by feeding `update()` a snapshot with `new_alert` set:
rows went 26 -> 27, the new row had `is-new`, the toast read `Over capacity Main Zone 7/4 people`.

### Why the toast exists at all

The alert log is in the right-hand column. An operator watching the **video** is looking at the
left. A log entry they never see has not alerted anybody. The toast appears where the eye already
is, and it is `aria-live="assertive"`, so a screen reader interrupts to read it.

---

## 8. Everything else, briefly

### 8.1 The first load, in parallel

```js
const jobs = {
  zones:   getJson("/api/zones"),
  alerts:  getJson("/api/alerts?limit=50"),
  history: getJson("/api/history?minutes=10"),
  sources: getJson("/api/sources"),
};
const results = await Promise.allSettled(Object.values(jobs));
```

`allSettled`, not `all`: if `/api/history` fails and the other three succeed, the dashboard still
appears with gauges, alerts and a video. Only the chart is missing, and the error bar names it.
`Promise.all` would have thrown away all four results.

Example: history times out -> gauges show, 50 alerts show, error bar says
*"Could not load: history. The page will update as soon as the engine answers."*

### 8.2 The history prefill

`GET /api/history` returns flat rows: `{ ts, zone, count }`, where one row per timestamp has
`zone = "ALL"` for the total. `prefillChart` groups them by timestamp:

```
2026-11-10T09:03:21+00:00, ALL,          7   -> total 7
2026-11-10T09:03:21+00:00, Main Zone,    7   -> zone 7
```

Rows are grouped into `{ label, total, zones{...} }` and the last 120 are kept.

### 8.3 The source dropdown

```js
POST /api/source { "name": "normal.mp4" }
```

then: clear the chart, re-fetch `/api/zones?source=normal.mp4`, rebuild the gauges and the chart
datasets (a new clip can have a different number of zones), restart the stream.

While this runs, `app.switching = true` stops new snapshots from refilling the just-cleared chart,
the dropdown is disabled, and a shimmer with "Loading clip…" covers the frame. Verified live:
switching to `normal.mp4` produced `is-loading -> false`, an empty chart, then a rebuilt gauge
showing `/ 4`, and `videoSrc` with a new `t=` value.

### 8.4 The overlay chips

The overlays are drawn by **OpenCV on the server**, so they cannot be CSS. The flags travel in
the query string:

```
/video?boxes=1&zones=1&heat=0
```

Flipping Heatmap and Zones produced, in order:

```
/video?boxes=1&zones=1&heat=1&t=1
/video?boxes=1&zones=0&heat=1&t=2
```

The `t=` counter exists because the browser caches by URL. Two toggles in the same millisecond
would otherwise produce an identical URL and the browser would silently do nothing - which is why
it is a **counter**, not `Date.now()`.

`aria-pressed` is the only stored truth, so the chip's colour, its state and what a screen reader
announces cannot drift apart.

### 8.5 The evidence modal

Clicking a thumbnail opens a `<dialog>` with the full keyframe:

```
title: "Main Zone · 09:05:56"
meta:  "peak 8/4 · cleared"
image: /evidence/alert_24.jpg, naturalWidth 640
```

`.showModal()` is used rather than a hand-rolled overlay because the browser supplies focus
trapping, Escape-to-close and an inert backdrop. Clicking the backdrop closes it too: a click on
the backdrop lands on the `<dialog>` element itself, so `event.target === modal` is the test.

One delegated listener on the `<ul>` handles every thumbnail. Per-row listeners would be created
and destroyed twice a second as the list updates.

### 8.6 Reconnect with backoff

```
attempt 1 -> wait 1 s
attempt 2 -> wait 2 s
attempt 3 -> wait 4 s
attempt 4 -> wait 8 s
attempt 5+ -> wait 10 s   (capped)
```

Measured live by killing the server, watching the pill, then restarting it:

```
Connected -> Reconnecting ("Retrying in 1 s…")
           -> Reconnecting ("Retrying in 2 s…")
           -> ... capped at 10 s
server back -> Connected, delay reset to 1 s
```

The delay resets on **open**, not on the first message, so a fast recovery is not punished.

Two details worth defending to a panel:

* **`reconnectTimer` guard** - a second `close` event must not queue a second socket. Two sockets
  would double every render.
* **No third "Connecting" state** - a retry that briefly shows `Connecting` makes the pill
  flicker between three labels. After the first successful open, every retry is `Reconnecting`.

### 8.7 Errors

Every fetch goes through one wrapper:

```js
async function getJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(8000) });
  if (!response.ok) throw new Error(`Server said ${response.status} for ${url}`);
  return response.json();
}
```

`AbortSignal.timeout` matters: without it a hung request leaves a skeleton on screen forever.
The error bar has a **Retry** button that re-runs the four fetches (not a page reload, which would
also restart the video).

---

## 9. The bug that mattered most: a stale "Active"

This one is worth a paragraph of its own, because it is the kind of bug a panel will respect.

`GET /api/alerts` marks an alert active when `ended_at IS NULL`. The engine sets that column when
the alert clears - **but only if the engine is running when it clears**. A crashed or killed run
leaves rows open permanently. The local database had an alert from **two days earlier** still
carrying `ended_at = NULL`.

The result on screen: the alert log said `1 active`, the tab said `(1) Crowd Analytics`, and the
banner said nothing - because the *live* snapshot knew no zone was over capacity.

Two indicators disagreeing is worse than either one being wrong: after that, the operator trusts
neither.

The fix reconciles the database's opinion against the engine's:

```js
if (zone && (Number(zone.over_for) || 0) <= 0) {
  return { ...alert, active: false };
}
```

`over_for` is `0.0` **exactly** when the zone is not currently over capacity, so it is the
engine's own answer to "is this alert still firing?". A row the database calls open but the engine
contradicts is shown as **Cleared**.

It is skipped on the frame that carries `new_alert`, so a brand-new alert's Active tag is never
immediately overwritten by a snapshot taken a moment earlier.

Verified afterwards: `2 active` in the log, `(2) Crowd Analytics` in the tab, and
`CONGESTION: Main Zone 6/4 for 2 s` in the banner - three indicators agreeing. Then, when the
alert genuinely cleared on its own, all three went back to `0 active` and the plain title within
2 seconds.

---

## 10. How it was checked

Every check was run against the real server and the real engine on CPU, in the browser.

| Check | Result |
| --- | --- |
| WebSocket connects | pill `Connected`, KPI numbers changing |
| People count trail | `total_people` -> KPI card, verified against `/ws` payload |
| KPI count-up | animates, and always lands on the true value |
| Empty tab background | number still lands (the rAF fallback) |
| Gauge fill 0.5 | `stroke-dashoffset` **163.36** |
| Gauge fill 1.0 / 1.5 | both clamp to **0.00**, `OVER` arc red, card hot |
| Status chip | OK / NEAR / OVER matches `status_for` |
| Chart datasets | `Total`, `Main Zone`, `Capacity` |
| Chart cap | stopped at exactly **120** labels |
| Chart labels | video time (`00:11`), not wall time |
| Alert history prefilled | 50 rows fetched, 28 shown |
| New alert | row prepended, `is-new` flash, toast `Main Zone 7/4 people` |
| Tab title | `(1)` / `(2)` while active, plain name at zero |
| Evidence modal | opens, loads `alert_24.jpg` at 640 px, closes |
| Source switch | loading state, chart cleared, gauges rebuilt, stream restarted |
| Overlay chips | URL becomes `heat=1` / `zones=0` |
| Reconnect | 1 s -> 2 s -> 4 s -> capped 10 s, recovered on restart |
| Fetch failure | inline error bar with Retry, page still usable |
| Empty alert log | "No alerts. All zones normal." and title reset |
| 360 px | **0 px** horizontal overflow |
| Console | no errors |
| Unit tests | **54 passed** |
| Smoke test | **10/10 passed** |

---

## 11. What could go wrong (and the fix)

| Symptom | Cause | Fix |
| --- | --- | --- |
| Pill stuck on "Connecting" | server not running | start `start.bat`; the backoff retries by itself |
| Pill on "Reconnecting" for 10 s | server is restarting | expected; it reconnects within 10 s of the server returning |
| Numbers frozen but pill green | engine thread died | read the terminal for `[engine] stopped on ...` |
| KPI shows `0` forever | `fps`/`dwell` at engine start | correct - check again after 2 s |
| Chart empty after a switch | new clip has not published yet | it refills from the next snapshots |
| Two alerts show Active | a crashed run left `ended_at` NULL **and** the zone is genuinely over | the reconciliation keeps it only while `over_for > 0` |
| Banner says a zone is over but the gauge is not | impossible by construction: both read one snapshot | if seen, the browser is showing an old tab |
| "Could not load: history" | database locked or slow first query | press Retry |
| Video is a static frame | MJPEG connection dropped | toggle an overlay chip to force a new request |
| Alert thumbnails show a grey icon | the keyframe file is missing | check `evidence/`; the API still lists the row |

---

## 12. Five questions a panel may ask (with short answers)

1. **Why a WebSocket instead of polling?**
   Two messages a second at about 500 bytes is 250 B/s per tab. Polling would add a full HTTP
   request each time - headers alone are several times the payload - and the numbers would arrive
   in bursts rather than a steady beat.

2. **Why does the KPI animate at all, and why the timeout fallback?**
   The animation makes direction visible. The fallback exists because `requestAnimationFrame`
   stops for hidden tabs, and without it a number can freeze at an intermediate value. The
   animation is decoration; landing on the true number is the requirement.

3. **Why keep the chart to 120 points?**
   It is a moving window, not an archive. Four minutes at 2 s per sample is enough to see a crowd
   build and disperse, and keeping the array bounded stops the tab from slowly getting heavier
   during a long session. History lives in SQLite, not in the DOM.

4. **Why does the gauge read `fill` instead of computing count/capacity?**
   `fill` is computed in Python on the same line as `status`, so the ring and the chip cannot
   disagree. The ratio is also clamped to 1, because `6/4` must draw a full ring - an unclamped
   ratio gives a negative dash offset, which wraps around and draws an almost-empty ring.

5. **How do you know the "Active" tag is telling the truth?**
   Because it is reconciled against the live snapshot: a row the database calls open is only
   shown as Active while its zone reports `over_for > 0`. The database alone is not trusted -
   a killed process leaves rows open forever, and I found one from two days earlier in this very
   project.

---

## 13. Numbers to remember

- `WS_INTERVAL = 0.5 s` -> **2 snapshots per second**; payload about 500 bytes.
- KPI animation **300 ms**, easeOutCubic, with a **360 ms** guaranteed fallback write.
- Chart window **120 points**; capacity line at the largest zone capacity.
- Ring: `C = 2 * pi * 52 = 326.73`; `offset = 326.73 * (1 - clamp(fill, 0, 1))`.
  - fill 0.5 -> **163.36**; fill 1.0 or 1.5 -> **0.00**.
- Reconnect: **1 s -> 2 -> 4 -> 8 -> 10 (cap)**; resets on open.
- Toast **5 s**; new-row flash **1.6 s**; alert log keeps the newest **50**.
- Fetch timeout **8 s**; first load runs **4 fetches** with `Promise.allSettled`.
- Status: `count > capacity` -> OVER; `count >= 0.8 * capacity` -> NEAR; else OK.
- Measured: alert fires at video **31.5 s**, peak **8** in a capacity-**4** zone.
- Engine on CPU: about **8 fps**.
- Tests: **54 unit**, **10/10 smoke**.
