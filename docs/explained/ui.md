# Step P6 - The dashboard UI with sample data (explained for a beginner)

This note explains every file and function written in step P6, in plain English, with a tiny
number example for each idea. Read it once, then explain it out loud in your own words.

Three files, no others:

| File | What it is | Size |
| --- | --- | --- |
| `static/style.css` | the design system: colours, shapes, animations | ~18.5 KB |
| `static/index.html` | the page structure: which panel goes where | ~14.9 KB |
| `static/app.js` | the sample data and the functions that draw it | ~26.2 KB |

Nothing in the backend changed. The engine, the database and the API from P5 are untouched; the
dashboard is still fed by a hard-coded object called `SAMPLE`.

---

## 1. What this step does, in five sentences

1. **`style.css`** declares the whole look once, as CSS variables in `:root`, so re-theming the
   product is a single edit.
2. **`index.html`** lays out a sticky top bar, a congestion banner, four KPI cards, a 12-column
   grid holding the video and the chart on the left and the gauges and alert log on the right.
3. **`app.js`** holds one object, `SAMPLE`, with the same field names the real engine will send,
   plus small functions (`renderKpis`, `renderGauges`, `renderAlerts`, `renderChart`) that draw it.
4. **`static/vendor/`** stays empty: Tailwind, Chart.js and Inter come from CDNs, and every icon is
   a four-line inline `<svg>`.
5. **The next step** replaces `SAMPLE` with the first WebSocket snapshot and calls `renderAll` with
   it. No layout code changes.

---

## 2. The shape of the page

```
+--------------------------------------------------------------+
| sticky bar: logo  Crowd Analytics  [Track A]   source  LIVE  |
|                                                       8.4 fps |  clock
+--------------------------------------------------------------+
| CONGESTION: Main Zone 12/10 for 12 s        <- hidden when OK |
+--------------------------------------------------------------+
| [People now] [Peak] [Average dwell] [Processing FPS]          |  4 KPI cards
+-----------------------------------+--------------------------+
| Live feed (16:9)                  | Zones                    |
| overlay chips + fullscreen        | (ring gauges, 2 across)  |
|-----------------------------------|--------------------------|
| Headcount chart + capacity line   | Alert log (scrolls)      |
+-----------------------------------+--------------------------+
```

The left block is **8 of 12 columns**, the right block is **4 of 12**. Measured at a 1024 px
window: the grid resolves to twelve 71 px columns, the left block gets `8 x 71 + gaps = 652 px`
and the right block gets `4 x 71 + gaps = 320 px`. At 360 px there is no room for twelve columns,
so the whole grid becomes **one** column of 321 px and the right block moves *below* the left one.

---

## 3. `static/index.html` - section by section

### 3.1 The three CDNs

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:...&display=swap" rel="stylesheet">
```

* **Tailwind** is used only for layout: `grid`, `flex`, `gap-3`, `lg:col-span-8`. It never decides
  a colour; those live in `style.css`.
* **Chart.js** draws the headcount line. It is the only charting library.
* **Inter** is the font; if the CDN is blocked the CSS falls back to Segoe UI, so the page still
  works offline-ish, just in a different typeface.

The console prints one warning, `cdn.tailwindcss.com should not be used in production`. That is
expected for a 2-day project and is the only message in the console.

### 3.2 Sticky top bar

`sticky top-0 z-40` keeps the bar at the top while the page scrolls, and `z-40` is higher than
every card so a card can never scroll *over* the bar. It contains:

* the **logo mark** - three vertical bars of rising height, an inline SVG;
* the product name and the `Track A` tag;
* the **source dropdown**, whose `<option>`s are filled by `renderSources()`;
* the **LIVE pill**, a solid green dot with an animated ring;
* the **FPS chip** and the **clock**.

At 360 px the tag, the LIVE pill and the clock are hidden and the dropdown is capped at 132 px. That
is a deliberate trade: the product name is the one thing that must stay readable, and without the
cap the dropdown squeezed it down to a single letter `C`, which looks like a bug.

### 3.3 Congestion banner

```html
<div id="congestion-banner" class="banner" role="status" aria-live="polite" hidden>
```

* `hidden` in the markup means it is invisible on first paint, so the page never flashes a stale
  warning before the first data arrives.
* `role="status"` + `aria-live="polite"` make a screen reader announce the warning when it appears,
  without interrupting whatever it is currently reading.
* The red gradient, the pulsing triangle and the text are all CSS plus `renderBanner()`.

### 3.4 The temporary dev cluster

Four dashed-outline buttons: `Banner: OK`, `Banner: OVER`, `Show skeletons`, `Empty alert log`.
They exist **only** so every visual state can be demonstrated without waiting for a live event.
`bindDevControls()` wires them. **They are deleted in P7.**

### 3.5 KPI cards

Each card is `article.glass.kpi-card` with a fixed internal order: icon badge, big number, label,
grey caption. The number and the caption carry `data-kpi="people"` and
`data-kpi-caption="people"` attributes so `setKpi()` can find them without an id per element.

Why attributes and not ids: four cards times two changing fields would be eight ids to invent,
type correctly, and keep in sync. One attribute name plus a key is one pattern reused four times.

### 3.6 Video card

`aspect-ratio: 16 / 9` with `width: 100%` means the frame is always the right shape: at 652 px wide
it is 367 px tall, at 321 px wide it is 181 px tall. No JavaScript measures anything.

On top of the frame sit three layers:

| Layer | Position | Why |
| --- | --- | --- |
| `<img id="video">` | `inset: 0`, `object-fit: contain` | the MJPEG stream in P7 |
| `.video-idle` | `inset: 0`, centred | "Video appears here" until a stream exists |
| `.overlay-toggles` | bottom-left | three chips over a blurred dark plate |
| `#fullscreen` | top-right | one icon button |

`object-fit: contain` letterboxes rather than crops: a detection box drawn on the frame would be in
the wrong place if the frame were cropped.

One subtle fix: an `<img>` with **no `src`** makes browsers draw a broken-image glyph plus the alt
text, which sat on top of the placeholder. The rule

```css
.video-frame img:not([src]) { display: none; }
```

hides it only while it has no source, with no JavaScript involved.

### 3.7 Headcount chart card

A `<canvas>` inside a `height: 190px` wrapper. The height must be on a **wrapper**, not the canvas:
Chart.js with `maintainAspectRatio: false` reads the parent's height, and a canvas given a height
directly fights it and grows on every resize.

The legend is written as HTML in the card header, including the dashed red capacity swatch. That is
why `plugins.legend.display` is `false` in the Chart.js config: one legend, written where it can be
styled with the same tokens as everything else.

### 3.8 Zone gauges

`#zone-gauges` is a two-column grid of `.gauge-card`s, filled by `renderGauges()`. Two placeholders
with shimmer bars are in the markup so the card is never empty. The header chip
(`#zones-summary`) reads `1/2 over` or `all normal`.

### 3.9 Alert log

`<ul class="alert-list" aria-live="polite">` with `max-height: 342px; overflow-y: auto`, so a long
history scrolls inside its card instead of pushing the whole page down. Each row is built by
`renderAlerts()`.

---

## 4. `static/style.css` - the parts worth explaining

### 4.1 One place for every colour

```css
:root {
  --bg: #070b14;  --panel: #0d1424;
  --card: rgba(17, 26, 46, 0.72);
  --border: rgba(255, 255, 255, 0.08);
  --accent: #38bdf8; --ok: #22c55e; --warn: #f59e0b; --crit: #ef4444;
  --text: #e6edf7; --muted: #8fa3bf;
  --radius: 16px;
}
```

Every rule below refers to these names, never to a literal hex. Changing `--accent` to `#a78bfa`
re-themes the logo, the chips, the chart legend swatch and the focus ring in one edit.

### 4.2 The glass card

```css
.glass {
  background: var(--card);          /* rgba(17,26,46,0.72) */
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  backdrop-filter: blur(14px) saturate(150%);
}
```

`backdrop-filter` blurs **what is behind** the element. The card fill is only 72% opaque, so 28% of
the page shows through, blurred.

**Numeric example.** The page background is `#070B14` = `rgb(7, 11, 20)`; the card fill is
`rgb(17, 26, 46)` at alpha `0.72`. The flat colour the card ends up at is

```
R = 0.72 x 17 + 0.28 x  7 = 12.24 +  1.96 = 14.2
G = 0.72 x 26 + 0.28 x 11 = 18.72 +  3.08 = 21.8
B = 0.72 x 46 + 0.28 x 20 = 33.12 +  5.60 = 38.7
                  ->  rgb(14, 22, 39)  =  #0E1627
```

So the card reads as a slightly lighter navy than the page, which is exactly the "sheet of frosted
glass on a dark table" effect. The 14 px blur is what softens the two radial glows behind it into
smooth gradients instead of hard circles.

### 4.3 Tabular numbers

```css
.tnum { font-variant-numeric: tabular-nums; }
```

Most fonts draw `1` narrower than `0`. Without this rule the KPI "16" becomes "17" and the digits
shift left by a pixel every time the number changes, which reads as a wobble. Tabular figures make
every digit the same width, so numbers only change, they never move.

Example: `18` in proportional figures is about 27 px wide; `11` is about 22 px wide. In tabular
figures both are exactly 2 x 14.6 = 29.2 px, so a counter ticking 11 -> 18 does not shudder.

### 4.4 The LIVE pulse

```css
.live-dot { animation: pulse-ring 2s infinite; }
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0    rgba(34, 197, 94, 0.55); }
  70%  { box-shadow: 0 0 0 7px  rgba(34, 197, 94, 0);    }
  100% { box-shadow: 0 0 0 0    rgba(34, 197, 94, 0);    }
}
```

The dot never moves or scales. A translucent `box-shadow` ring grows from 0 to 7 px and fades to
zero, then restarts. Two reasons: `box-shadow` changes do not trigger layout, and growing a
*shadow* cannot push neighbouring pixels, so the bar's height is identical at every frame.

### 4.5 The ring gauge, step by step

The gauge is two `<circle>`s of radius 52 in a 120 x 120 viewBox, both with `stroke-width: 9`, both
rotated `-90deg` about the centre so the ring starts at 12 o'clock instead of 3 o'clock.

The dashed-stroke trick: a circle's outline can be turned into dashes with
`stroke-dasharray`. If the dash length equals the **circumference**, the single dash covers the
whole ring. Then `stroke-dashoffset` slides that dash backwards, hiding a slice of it.

**The circumference.**

```
C = 2 x pi x r = 2 x 3.14159 x 52 = 326.73
```

**Example A - `Main Zone`, 12 people in a capacity of 10.**
Fill fraction is clipped at 1, because a ring cannot be more than full:

```
fraction = min(12 / 10, 1) = 1.00
offset   = C x (1 - fraction) = 326.73 x 0 = 0.00
```

`0.00` is what the live page reports. The whole ring is visible, painted `--crit` red, and the
`OVER` chip carries the information that the count exceeds capacity.

**Example B - `Entrance`, 4 people in a capacity of 8.**

```
fraction = min(4 / 8, 1) = 0.50
offset   = 326.73 x 0.50 = 163.36       <- exactly half the ring hidden
```

For a 3-of-8 zone: `326.73 x (1 - 0.375) = 204.21`, so a little more than half the ring is hidden.
Both numbers (`0.00` and `163.36`) were read back from the rendered DOM, not copied from the code.

**Why the clip at 1 matters.** Without `min(..., 1)`, `12/10` gives `offset = 326.73 x (1 - 1.2) =
-65.35`. A negative dash offset wraps around and draws a small arc *stuck to the start line*, which
looks like a nearly empty ring for the busiest zone on screen - the opposite of the truth.

The CSS transition `stroke-dashoffset 0.9s` is what makes the ring sweep in on first paint, from
fully hidden to its value.

### 4.6 Status chips

Three variants, each a colour pair (text + tinted background + border) derived from the same three
semantic tokens: `.ok` green, `.near` amber, `.over` red. The class name comes from
`statusClass()`, so the word `OVER` in the data and the red chip on screen can never disagree.

### 4.7 Skeletons

```css
.skeleton { position: relative; overflow: hidden; background: rgba(255,255,255,0.055); }
.skeleton::after {
  content: ""; position: absolute; inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.09), transparent);
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer { 100% { transform: translateX(100%); } }
```

A pseudo-element slides from `-100%` to `+100%` inside a box that clips it. Because it translates
rather than resizes, nothing around it moves. The page uses three shapes:
`skeleton-ring` (96 px circle), `skeleton-line` (10 px bar) and `skeleton-row` (46 px rectangle),
plus `skeleton-value` for the KPI numbers.

### 4.8 Focus and reduced motion

```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

`:focus-visible` matches keyboard focus only, so mouse users never see a ring and keyboard users
always do. `outline-offset` keeps the ring outside the element instead of clipping it.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
  .skeleton::after { display: none; }
}
```

The durations are set to almost zero rather than to `none`: a `none` duration can leave a
transition in an indeterminate state in some browsers, while `0.001ms` finishes instantly and
deterministically. The ring still shows the correct value, it simply appears without sweeping.

### 4.9 Responsive rules

Two breakpoints, one of them Tailwind's.

| Width | What happens | How |
| --- | --- | --- |
| `< 640px` | tag, LIVE pill hidden; header subtitle hidden | Tailwind `hidden sm:inline-flex` |
| `< 768px` | FPS chip hidden | `hidden md:inline-flex` |
| `< 1024px` | main grid is one column; KPIs are 2x2 | `grid-cols-1` / `grid-cols-2` |
| `>= 1024px` | 12 columns; KPIs 4 across | `lg:grid-cols-12`, `lg:grid-cols-4` |
| `<= 420px` | rings 96 px, KPI digits 25 px, source select 132 px, clock hidden | `@media (max-width: 420px)` |

Verified numbers at both sizes, measured in the browser rather than estimated:

| | 360 px | 1024 px |
| --- | --- | --- |
| Horizontal overflow | **0 px** | **0 px** |
| KPI card width | 155.3 px | 237 px |
| Main grid | one 321 px column | 12 x 71 px |
| Ring width | 96 px | 118 px |
| Chart height | 190 px | 190 px |

"Overflow 0" is the check that matters most: `documentElement.scrollWidth - clientWidth` must be 0,
otherwise the page scrolls sideways on a phone and the sticky bar looks broken.

---

## 5. `static/app.js` - every function, and why it exists

### 5.1 The data contract

```js
SAMPLE = {
  source: "crowded.mp4",
  sources: ["crowded.mp4", "mid.mp4", "normal.mp4"],
  fps: 8.4,
  peakPeople: 15,
  zones:  [{ name, count, capacity, status, overFor, avgDwell, maxDwell }],
  alerts: [{ id, zone, startedAt, peak, capacity, active, keyframe }],
  chart:  { labels: [...60...], values: [...60...] },
  chartCapacity: 10,
}
```

These key names were chosen to match the P5 engine snapshot where it already had a name:
`name`, `count`, `capacity`, `status`, `over_for`, `avg_dwell` become `overFor`, `avgDwell` in
JavaScript. The next step is then a mapping exercise, not a rewrite.

`overFor` is not decoration: it is the field the banner reads, and it is the same number
`AlertDebouncer.over_for` publishes.

### 5.2 Render helpers

| Function | What it does | Tiny example |
| --- | --- | --- |
| `seeded(seed)` | deterministic pseudo-random in [0,1) | `seeded(3)` is the same number on every reload, so a doc screenshot always matches |
| `buildHeadcountSeries()` | 60 points, 2 s apart, ending now | `trend = 6 + 5 x sin((i/59) x pi)`, so point 0 is ~6, point 30 is ~11, point 59 is ~6 |
| `escapeHtml(v)` | replaces `& < > "` | `Main & Co` becomes `Main &amp; Co` |
| `statusClass(s)` | `"OVER"` -> `"over"` | one lowercase class name |
| `statusIcon(s)` | returns the right 3-line SVG | circle+`!` for OVER, triangle for NEAR, tick for OK |
| `formatDwell(s)` | compact seconds | `18.4 -> "18 s"`, `6.2 -> "6.2 s"` |

`escapeHtml` is not paranoia: zone names come from `zones.json`, which a person edits by hand, and
in P7 the same text arrives over a WebSocket. A name containing `<` would otherwise inject markup.

`formatDwell` switches precision at 10 s on purpose. Under ten seconds the tenth matters ("6.2 s"
versus "6 s" is a visible difference); over ten it does not, and rounding keeps the caption short
enough for a narrow gauge card.

### 5.3 `renderKpis(data)` and `setKpi(key, value, caption)`

```js
const totalPeople = data.zones.reduce((sum, zone) => sum + zone.count, 0);   // 12 + 4 = 16
```

`renderKpis` computes four numbers and hands each to `setKpi`, which finds the element by
`[data-kpi="people"]` and writes it.

The dwell figure is **not** the mean of the zone means. It is the **busiest zone's** dwell:

```
zones: Main Zone avg 18.4, Entrance avg 6.2
mean of means = (18.4 + 6.2) / 2 = 12.3
chosen value  = max(18.4, 6.2)    = 18.4  ->  "18 s"
```

Why: a bottleneck is a *place*. Averaging a jammed zone with a quiet one produces 12.3 s, a number
that describes neither zone and hides the problem the dashboard exists to show.

`setKpi` special-cases dwell so the unit renders as a small grey span (`18` + `s`), which is why the
KPI reads `18s` in the DOM text but looks like "18 s" on screen.

### 5.4 `renderGauges(zones)`

Builds one SVG ring per zone with the arithmetic from section 4.5, then sets the summary chip:

```
zones = [Main Zone OVER, Entrance OK]
overCount = 1                    ->  chip "1/2 over" in red
zones = [Entrance OK, Other OK ]
overCount = 0                    ->  chip "all normal" in green
```

The `aria-label` on each ring spells the whole reading out -
`"Main Zone: 12 of 10 people, OVER"` - so a screen-reader user gets the same information as a
sighted one, not "graphic".

### 5.5 `renderAlerts(alerts)`

Two paths:

* **Empty** -> one `<li class="empty-state">` with a tick and the words
  *"No alerts. All zones normal."* An empty list looks identical to a broken panel; this tells them
  apart in three words.
* **Non-empty** -> one `<li class="alert-row">` per alert.

Severity is **derived**, not stored:

```js
ratio = peak / capacity
severity = active ? "crit" : ratio >= 1.3 ? "crit" : "warn"
```

Example: `peak 13 / capacity 10 = 1.30` -> `crit` (red bar).
Example: `peak 11 / capacity 10 = 1.10` -> `warn` (amber bar).
Deriving it means there is exactly one place that decides a colour, and it cannot go stale.

The thumbnail shows `alert.keyframe` when the backend supplies one (`/evidence/alert_1.jpg`) and a
grey image glyph otherwise, so the layout never jumps between the two states.

### 5.6 `renderChart(series, capacity)`

```js
if (headcountChart) { headcountChart.data = config.data; headcountChart.update("none"); return; }
headcountChart = new Chart(context, config);
```

The instance is cached in a module-level variable. Calling `new Chart()` on the same canvas every
refresh leaks contexts until the tab stutters, so after the first draw it only replaces `data`.

Two datasets: the people line (filled with a vertical gradient, `tension: 0.35`, `pointRadius: 0`)
and a flat capacity line (`borderDash: [5, 4]`). `pointRadius: 0` matters - 60 visible dots would
read as a scatter plot instead of a trend.

### 5.7 `renderBanner(problem)` and `worstZone(zones)`

`worstZone` filters to `status === "OVER"` and keeps the one with the largest `overFor`. The banner
then reads:

```
CONGESTION: Main Zone 12/10 for 12 s
            ^name    ^count/capacity  ^round(overFor)
```

`Math.round` is there because `over_for` is a float like `12.43`; "for 12.43 s" is noise in a
one-line alarm.

**Bug found and fixed during this step.** The first version read `problem.zone` while zones carry
`name`, so the banner printed `CONGESTION: undefined 12/10`. The fix was to use `name` on both
sides, which is also the key the P5 snapshot sends, so P7 needs no translation. Verified in the
browser afterwards: `"CONGESTION: Main Zone 12/10 for 12 s"`.

### 5.8 `startClock()`, `bindToggle()`, `bindFullscreen()`

* `startClock` paints the time once, then every 1000 ms via `setInterval`. It uses
  `toLocaleTimeString("en-GB", { hour12: false })` so the format is `21:20:13` regardless of the
  machine's locale.
* `bindToggle(id, key)` flips one entry of the shared `overlays` object and writes the result to
  `aria-pressed`. CSS colours the chip from that attribute, so the visual state and the announced
  state cannot drift apart. In P7 the same object becomes the `/video?boxes=1&zones=1&heat=0`
  query string.
* `bindFullscreen` calls `requestFullscreen()` on `.video-frame`, not on the `<img>`. The overlay
  chips are siblings of the image, and fullscreening the image would leave them behind.

### 5.9 `showSkeletons()` and `renderSources()`

`showSkeletons` replaces three regions with shimmer placeholders: the two rings, three alert rows,
and the four KPI numbers (so no stale figure is visible while loading). It also sets both summary
chips to `…`.

`renderSources(names, current)` fills the `<select>` and updates the small chip above the video.
`current` gets the `selected` attribute, so the dropdown opens on the clip that is actually playing.

### 5.10 `renderAll(data)` - the single entry point

```js
function renderAll(data) {
  renderKpis(data);
  renderGauges(data.zones);
  renderAlerts(data.alerts);
  renderChart(data.chart, data.chartCapacity);
  renderBanner(worstZone(data.zones));
}
```

Why one entry point: if each panel fetched or computed its own numbers, the screen could show a
banner from 10.5 s next to a chart point from 10.0 s. One call with one snapshot means every panel
describes the same instant. **P7 changes exactly one line here** - the argument - and one line in
`boot()`.

### 5.11 `bindDevControls()` and `boot()`

`boot()` starts the clock, fills the source list, wires the toggles, the fullscreen button and the
dev buttons, then shows skeletons and calls `renderAll(SAMPLE)` after **700 ms**.

The 700 ms is not laziness. On a fast local machine the data would otherwise appear before the
first paint, and the skeleton state would be impossible to review at all. In P7 the timeout is
replaced by "wait for the first WebSocket message".

The dev buttons are temporary previews:

| Button | Effect | Restores itself? |
| --- | --- | --- |
| `Banner: OK` | `renderBanner(null)` hides the banner | no (stays hidden) |
| `Banner: OVER` | `renderBanner(SAMPLE.zones[0])` | no |
| `Show skeletons` | `showSkeletons()`, then `renderAll(SAMPLE)` after 1.6 s | yes |
| `Empty alert log` | `renderAlerts([])`, then the real 6 alerts after 2.2 s | yes |

The two timed ones restore themselves so they behave like previews rather than one-way switches.

---

## 6. How it was checked

| Check | Result |
| --- | --- |
| Page loads at desktop width | 4 KPI cards, chart, 2 rings, 6 alerts |
| Console errors | none; only the expected Tailwind CDN notice |
| Banner text | `CONGESTION: Main Zone 12/10 for 12 s` |
| KPI values | people 16, peak 15, dwell 18 s, fps 8.4 |
| Ring offsets in the DOM | `["0.00", "163.36"]` - matches the hand arithmetic |
| Alert summary | `1 active / 6` |
| Empty state | `No alerts. All zones normal.` |
| Skeleton state | 4 KPI bars, 2 rings, 3 rows |
| Overlay chips | `aria-pressed` flips `false` -> `true` -> `false` |
| 360 px overflow | 0 px; KPIs 2x2; grid one column |
| 1024 px overflow | 0 px; KPIs 4 across; grid 8+4 |
| Unit tests | 54 passed |

Two layout bugs were found this way and fixed: the broken-image glyph over the video placeholder
(fixed with `img:not([src])`), and the product name truncating to `C` at 360 px (fixed by hiding the
tag and clock and capping the dropdown).

---

## 7. What could go wrong (and the fix)

| Symptom | Cause | Fix |
| --- | --- | --- |
| Page is unstyled, plain black text | `style.css` not served | open `/static/style.css` directly; if 404, check `app/main.py` mounts `/static` |
| Cards have no blur, just flat navy | browser without `backdrop-filter` | expected on old browsers; the flat fill still looks fine |
| Chart card grows on every resize | height set on the `<canvas>` | keep the 190 px on the wrapper `div` |
| Chart draws twice, flickers | `new Chart()` per update | reuse the cached `headcountChart` |
| Banner says `undefined` | reading `zone` instead of `name` | fixed in 5.7 |
| Ring looks empty for an over-capacity zone | negative `stroke-dashoffset` | the `Math.min(..., 1)` clip |
| Page scrolls sideways on a phone | one unbreakable element wider than the viewport | check `scrollWidth - clientWidth`; the header is the usual culprit |
| Text is in a different font | Google Fonts blocked | the CSS falls back to Segoe UI; nothing breaks |
| Nothing appears for a second | `boot()` waits 700 ms on purpose | expected |

---

## 8. Five questions a panel may ask (with short answers)

1. **Why not React?**
   The whole UI is one page, one data object and five render functions. React would add a build
   step, a package tree and a mental model, in exchange for saving about 200 lines of
   `innerHTML`. Plain functions are also easier to read line by line when explaining to a panel.

2. **Why does the ring use `stroke-dashoffset` instead of SVG arcs?**
   An arc needs trigonometry to convert a fraction into start/end angles and large-arc flags, and it
   breaks at 100%. A dashed circle needs one multiplication: `offset = C x (1 - fraction)`. Fewer
   lines, no special cases.

3. **Why sample data instead of wiring the WebSocket immediately?**
   Separating "does it look right" from "does it update" means a styling bug and a data bug can
   never be confused. It also let the layout be checked at 360 px and 1024 px without waiting 35
   seconds for an alert to fire.

4. **How do you know the layout does not overflow on a phone?**
   Not by eyeballing a screenshot: `documentElement.scrollWidth - clientWidth` was measured inside
   360 px and 1024 px frames and was `0` at both. That single number is the objective test.

5. **Where does the dashboard get its numbers in the final version?**
   `renderAll(snapshot)` over the `/ws` WebSocket from P5, roughly every 0.5 s. The snapshot
   already carries `zones[].name/count/capacity/status/over_for/avg_dwell`, `total_people`,
   `peak_people` and `fps`, which is why the sample object was shaped to match.

---

## 9. Numbers to remember

- Grid: **12 columns** at >= 1024 px -> **8 + 4** (652 px + 320 px); **1 column** below.
- At 360 px: zero horizontal overflow, KPI cards 2x2, rings 96 px, chart 190 px tall.
- Ring: `r = 52`, `C = 2 x pi x 52 = 326.73`; `offset = 326.73 x (1 - fraction)`.
  - 12/10 -> fraction clipped to 1 -> **offset 0.00**
  - 4/8 -> fraction 0.50 -> **offset 163.36**
- Glass card: `rgb(17,26,46)` at `0.72` over `#070B14` -> **`#0E1627`**; blur 14 px.
- Sample data: 2 zones (**12/10 OVER, overFor 12** and **4/8 OK**), **6 alerts** (1 active),
  **60** chart points, capacity line at **10**, peak **15**, fps **8.4**.
- Dwell shown is the **busiest** zone (18.4 s -> "18 s"), not the mean of means (12.3 s).
- Severity: active -> crit; `peak/capacity >= 1.3` -> crit; otherwise warn.
- States: skeleton (4 numbers, 2 rings, 3 rows) and empty alert log.
- Unit tests: **54**.
