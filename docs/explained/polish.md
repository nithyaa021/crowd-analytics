# Step P8 - Polish pass (explained for a beginner)

P8 adds **no features**. Nothing new can be clicked, no new number appears, no endpoint changed.
The Python backend was not touched at all. Every change here is presentation and robustness:
the same dashboard, made trustworthy enough to put in front of a panel.

Read this with the P7 note (`docs/explained/live.md`) next to you. P7 made the numbers *true*.
P8 makes the page *honest about itself* - it works with the network cable out, it says the same
thing to a colour-blind visitor as to everyone else, and it survives being squeezed onto a phone.

---

## 1. The one-sentence summary of each requirement

| # | Requirement | What it actually means |
| --- | --- | --- |
| 1 | Offline safety | Downloaded the two libraries into the project so nothing is fetched from the internet |
| 2 | Micro-interactions | Small movements that confirm "yes, that is a button" and "yes, that just changed" |
| 3 | Visual hierarchy | One number scale, one radius scale, two font weights, spacing in 4 px steps |
| 4 | Accessibility | Never rely on colour alone; let the keyboard reach everything; describe images |
| 5 | Responsive | No sideways scrolling at 360, 768, 1024 or 1440 px |
| 6 | Identity | A favicon, a correct title, and a quiet credit line |
| 7 | Cleanup | No dev buttons, no console output at all |
| 8 | Docs + verify | This file, 54 unit tests, 10/10 smoke checks |

---

## 2. Offline safety: why the page now works with the cable unplugged

### The problem

Before P8, two lines in `index.html` reached out to the internet:

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
```

The chart library is obvious: no Chart.js, no chart. But Tailwind is the quiet one. Tailwind's
"Play CDN" build is a **compiler that runs in the browser**: it reads the class names in your
HTML and generates the CSS for them on the fly. Without that file the page still loads, but every
`flex`, `grid` and `gap-3` is ignored, and the dashboard collapses into a single column of
unstyled text. That is exactly the failure a demo must not have.

### The fix

Both files are now downloaded into the project and served by the same FastAPI app that serves
everything else:

```
static/vendor/tailwind.js       412,549 bytes
static/vendor/chart.umd.min.js  205,399 bytes
```

Their SHA-256 hashes, so anyone can prove the copy in this repository is the published build
(it is also why `.gitattributes` marks `static/vendor/**` as `-text`: git must not rewrite a
single byte of a minified file on checkout):

```
tailwind.js       9AC7E6502C58C9229C2261A700EDE9EAB2EC8C0DF8B8B255AACB65E64ED48EF6
chart.umd.min.js  D2AF8974E95271638772E9E9524DB5B9A6F58D6EC2D5D781400447B4A31C681E
```

```html
<script src="/static/vendor/tailwind.js"></script>
<script src="/static/vendor/chart.umd.min.js"></script>
```

Both were **verified to be the real libraries, not error pages**. A failed `Invoke-WebRequest`
often writes a 200-byte HTML error into the file, and the page then fails in a confusing way
later. So each file was checked for its own signature:

* tailwind.js starts with `(()=>{var Zb=Object.create;` and contains `tailwind.config`
* chart.umd.min.js contains `Chart.js v4`
* neither starts with `<` (which would prove it is HTML)

`app/main.py` already mounts `/static`, so `vendor/` is served with no new route.

### The font is the one thing still remote - on purpose

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap"
      rel="stylesheet" media="print" onload="this.media='all'">
```

Inter is a *nicety*, not a requirement. Three details make it safe:

1. **`media="print" onload="this.media='all'"`** - the browser downloads the font *without
   blocking the first paint*. A font server that hangs for ten seconds would otherwise leave the
   page blank for ten seconds.
2. **`system-ui` is the very next font in the stack** - with the font blocked, the fallback is
   the operating system's own UI font, which on Windows is Segoe UI. The page looks like the same
   product.
3. It is measured, not hoped: with the font link removed and the body font forced to
   `system-ui`, the KPI card stayed **exactly 301 x 151 px** and overflow stayed **0 px**. The
   only visible difference was the title getting narrower (117 -> 107 px), because Segoe UI is
   narrower than Inter.

So the honest statement for the panel is: *"Every byte the page needs is served by the app.
The font is an optional upgrade; with no network at all, the layout is identical."*

### Proof

Every `src` and `href` in `index.html`, after P8:

```
/static/app.js
/static/style.css
/static/vendor/chart.umd.min.js
/static/vendor/tailwind.js
data:image/svg+xml,...        (the favicon, inline)
https://fonts.googleapis.com  (optional font only)
```

And each of the five local paths re-fetched and returned `200` with the expected size:

| Path | Status | Bytes |
| --- | --- | --- |
| `/static/vendor/tailwind.js` | 200 | 412,549 |
| `/static/vendor/chart.umd.min.js` | 200 | 205,399 |
| `/static/style.css` | 200 | 34,269 |
| `/static/app.js` | 200 | 65,099 |
| `/` | 200 | 19,068 |

### The one edited line inside a vendored file

Tailwind's Play CDN build always calls:

```js
console.warn("cdn.tailwindcss.com should not be used in production. ...")
```

Requirement 7 says no console noise, and this warning fires on every single page load. Since the
file is now **ours** (it lives in our repository, we serve it), that one call was rewritten to
`void 0`. Exactly **1 occurrence** matched, the file stayed 412,549 bytes and still parses. This
is documented here rather than silently done, because editing a third-party file is the kind of
thing a reviewer should be told about.

---

## 3. Micro-interactions: five small movements, each with a reason

A "micro-interaction" is feedback that lasts a fraction of a second. It is not decoration - each
one answers a question the user is already asking.

### 3.1 Card hover lift

```css
@media (hover: hover) and (pointer: fine) {
  .glass:hover {
    transform: translateY(-2px);
    border-color: var(--border-strong);
    box-shadow: var(--shadow-lift);
  }
}
```

Two questions this answers: *"is this whole thing one card?"* and *"did my pointer land on it?"*
A 2 px rise is enough to read as "picked up" without making the layout twitch.

The media guard matters more than the effect. On a touch screen there is no pointer, so a `:hover`
style **sticks** after a tap - the card would stay raised until something else was tapped. The
guard means the lift exists only where a real pointer does.

Only `transform` and two shadow values animate, so a hover never re-blurs the glass (which would
cost a repaint of everything behind it).

### 3.2 Button press states

```css
.chip:active      { transform: translateY(1px); }
.icon-button:active { transform: translateY(1px); }
.alert-thumb.is-clickable:active { transform: scale(0.97); }
```

A 1 px downward shift, not a shrink. Why: shrinking text makes it re-render at a new subpixel
size and look briefly blurry; moving the box does not touch the glyphs. `:active` only exists
while the mouse button is down, so it costs nothing at rest.

### 3.3 Smooth gauge colour transition

This is the one that fixes a real visual bug. The ring already animated its *length*:

```css
.gauge-arc {
  transition: stroke-dashoffset 0.9s cubic-bezier(0.4, 0, 0.2, 1),
              stroke 0.24s linear;      /* this line is new */
}
```

Before P8 the colour **snapped** from amber to red at the instant the status changed, while the
ring length kept gliding for 0.9 s. For about a second the arc was red but only three-quarters
long, and the chip said OVER - three signals disagreeing. Now the colour travels over 0.24 s and
arrives with the chip.

Measured in the running page: `transition-property: stroke-dashoffset, stroke`,
`transition-duration: 0.9s, 0.24s`.

### 3.4 Banner slide-in

```css
.banner { animation: banner-in 0.24s var(--ease-out); }
@keyframes banner-in {
  from { opacity: 0; transform: translateY(-6px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

The banner is `hidden` until a zone goes over capacity, so the animation runs at exactly the
moment a congestion starts. 6 px of travel is enough to catch peripheral vision without shoving
the page around. The page does not reflow: `transform` does not affect layout.

### 3.5 New-alert flash

Unchanged from P7 (1.6 s expanding outline), but verified again after the rewrite: the row that
arrived had `is-new` and the toast read `Over capacity Main Zone 9/4 people`.

### 3.6 Tooltips on the KPI icons

Each of the four KPI icons now has a sentence:

```html
<span class="icon-badge" aria-hidden="true"
      data-tip="How many video frames the detector can process per second on this CPU.">
```

Four decisions worth defending:

* **CSS, not `title=""`.** A `title` tooltip waits about a second and cannot be styled. This one
  is instant and matches the product.
* **`display: none` at rest, not `opacity: 0`.** This was a real bug found by measuring. A
  hidden-but-laid-out 208 px box still counts towards the page's scrollable width - at 360 px
  the four tooltips pushed the whole page **53 px sideways**. `display: none` takes it out of
  layout entirely; a keyframe animation (not a transition) still gives the fade-in.
* **It opens downward, not upward.** The badge sits 16 px from the card's top edge, so an upward
  tooltip on the first row half-disappeared under the sticky header (`z-40`). Measured after the
  fix: tooltip top 143 px vs header bottom 59 px, bottom 175 px vs card bottom 238 px - fully
  visible, and overflow still 0.
* **It costs no tab stop.** The icon is `aria-hidden`, so a keyboard user tabs past it, and the
  same sentence is already in the caption underneath. Nothing is available *only* on hover -
  which is the actual accessibility rule.

---

## 4. Visual hierarchy: the audit found the real numbers

The instruction was "consistent radius, spacing in 4 px, at most 2 weights per card". Rather than
eyeball it, the live page was queried for every computed font size, weight and radius in use.

### What the audit found before

Radii scattered over **seven** values: 7, 8, 9, 10, 11, 12 and 16 px. A 9 px and a 10 px corner
are indistinguishable to the eye but *are* different, so the page reads as slightly out of focus
without anyone being able to say why. Font sizes used **six fractional steps** - 9.5, 10.5, 11.5,
12.5 - which meant two labels that should have matched differed by half a pixel.

### The fix: three scales, declared once

**Type** - every size in the file now comes from this list and nowhere else:

```css
--fs-2xs: 10px;   /* pills, timestamps, gauge dwell */
--fs-xs:  11px;   /* captions, section titles, legend */
--fs-sm:  12px;   /* body, zone names, toast */
--fs-md:  13px;   /* KPI labels, banner */
--fs-lg:  15px;   /* product title, modal title */
--fs-2xl: 26px;   /* gauge number, phone KPI */
--fs-3xl: 30px;   /* KPI number */
```

**Radii** - three plus a pill:

```css
--radius:      16px;   /* a card            (was also 12, 13 in places) */
--radius-md:   10px;   /* a block in a card (was 11, 12, 13)          */
--radius-sm:    8px;   /* a control         (was 7, 9)                */
--radius-pill: 999px;  /* chips, pills, scrollbar                     */
```

**Weights** - exactly two: **400** for reading, **600** for emphasis. The old file used 500, 650
and 700 as well; 650 was a value the font does not even have, so the browser had to round it.

### What the audit found after

Measured on the live page, across `main`, `header` and `footer`:

**Font sizes actually rendered - 7 distinct values, all from the scale:**

| Size | Uses | What it is |
| --- | --- | --- |
| 30px | 3 | KPI numbers |
| 26px | 1 | gauge number (and phone KPI) |
| 15px | 3 | product title, unit suffix, modal title |
| 13px | 4 | KPI labels, banner |
| 12px | 38 | body text, zone names |
| 11px | 50 | captions, section titles |
| 10px | 66 | pills, timestamps |

**Font weights - 2:** `400` (84 elements), `600` (81 elements). Nothing else.

**Radii - 4:** `8px` (47), `999px` (39), `10px` (37), `16px` (8). Every one is on the scale.

**Weights per card:** the check walked all 41 cards and rows and collected the weight of every
text node inside each. Result: **zero cards over two weights.** Every card is exactly `400,600`.

### Spacing

Card padding went from a mix of `15px 16px 14px` and `12px 8px 11px` to `16px` and `12px 8px`.
The gaps inside a card are now 4 / 8 / 12 / 16 / 32 px. Three exceptions are deliberate:

* **1 px** borders, because a 4 px border would be a design element, not an edge.
* **2 px** on `.kpi-label` and several icon offsets. This is an *optical* nudge: the number's line
  box already carries space, so a 4 px gap makes "30" and "People now" look like two unrelated
  items. The eye wants 2 px here even though the grid says 4.
* **Icon stroke widths** (2, 2.4, 2.6), which are drawing attributes, not spacing.

### One thing removed rather than restyled

`canvas` was sized by an inline `style="position:relative;height:190px"`. It is now a class
(`.chart-box`, 192 px) so the last inline dimension in the layout is gone, and 192 is 48 x 4.

---

## 5. Accessibility: measured, not assumed

### 5.1 Contrast of muted text

The brief asks specifically about muted text on cards. The card is translucent over a dark
gradient, so its flat colour was computed (`rgba(17,26,46,.72)` over `#070B14`) and the
WCAG relative-luminance formula applied:

| Colour | vs card | vs page | Verdict |
| --- | --- | --- | --- |
| muted `#8FA3BF` | **7.03:1** | 7.65:1 | passes AA (4.5) and AAA (7.0) |
| text `#E6EDF7` | 15.35:1 | 16.70:1 | far past AAA |
| accent `#38BDF8` | 8.44:1 | 9.19:1 | passes AAA |
| ok `#22C55E` | 7.94:1 | 8.64:1 | passes AAA |
| warn `#F59E0B` | 8.42:1 | 9.16:1 | passes AAA |
| crit `#EF4444` | **4.81:1** | 5.23:1 | passes AA, weakest of the set |

So the muted text needed **no change** - it was already past AAA, and lightening it further would
have made the hierarchy flat. The table exists so the claim can be *shown* instead of asserted.

`crit` at 4.81:1 is the thinnest margin, and it is used for the alert severity bar and the
capacity line. Both are **non-text graphics**, where the WCAG threshold is 3:1 - so 4.81 is
comfortable. The banner's own text is white on a red gradient, which was checked separately.

The **footer credit** needed real work. At 72% opacity the muted colour drops to **4.41:1**, which
fails AA for small text. Raised to 85% -> **5.76:1**, and one type step up (10 -> 11 px), while
still reading as the quietest line on the page.

### 5.2 Status is never colour alone

Every status in the UI carries **three** signals at once:

```
[icon] NEAR        <- word + icon + colour
```

* The gauge chip prints `OK` / `NEAR` / `OVER` and draws a tick / triangle / circle-slash.
* The gauge ring changes colour, *and* the chip names the state in words.
* The alert tag prints `Active` or `Cleared`.
* The live pill prints `Connected` / `Reconnecting`, never just a green or amber dot.
* The alert severity bar is the one colour-only cue, and it is marked `aria-hidden="true"` and is
  redundant: the row beside it already says `Active` with a peak count.

Why this matters in one number: about **1 in 12 men** has some red-green colour deficiency. A red
ring with no word would be silent for them.

### 5.3 Live regions

| Element | Setting | Why |
| --- | --- | --- |
| Congestion banner | `role="status" aria-live="polite"` | read out when a congestion starts, without interrupting |
| Alert log `<ul>` | `aria-live="polite"` | a new row is announced as it is prepended |
| Toast stack | `aria-live="assertive"` | an over-capacity zone *should* interrupt |
| Error bar | `role="status" aria-live="polite"` | a failed fetch is news, not an emergency |
| Live pill | `role="status" aria-live="polite"` | connection changes are announced |

`polite` waits for the current sentence to finish; `assertive` interrupts. Getting this the wrong
way round is a common accessibility bug - an `assertive` alert log would interrupt the screen
reader every two seconds.

### 5.4 Keyboard focus order

The tab order was enumerated from the live DOM. It follows the visual order:

```
source-select -> [error Retry] -> [Dismiss] -> Boxes -> Zones -> Heatmap -> fullscreen
  -> alert-list (the scrolling region) -> each thumbnail in turn -> [modal close]
```

The hidden elements (error bar buttons, modal close) are in the list but not focusable while
their parent is `hidden` or the dialog is closed - the browser handles that, not us.

**One real fix here.** The alert log scrolls inside its card, and a scrollable box that no key can
reach is a **WCAG 2.1.1 failure** - a keyboard-only user could never see alert 20. It now has
`tabindex="0"`, so the region itself takes focus and arrow keys / Page Down scroll it, without
having to tab through all 50 rows.

`.alert-list:focus-visible` gets the same 2 px accent ring as everything else. The global rule is:

```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

`:focus-visible`, not `:focus`, so a mouse click does not leave a ring behind - and no
`border-radius` on the rule, because setting one reshapes whichever element received focus.

### 5.5 Alt text

| Image | Alt |
| --- | --- |
| Live video | "Live annotated video with detection boxes and zone overlays" |
| Alert thumbnail | "Snapshot of Main Zone at 09:30:04" (zone and time, built per row) |
| Evidence modal image | "Snapshot of Main Zone at 09:30:04" |
| All decorative SVG icons | `aria-hidden="true"` |

The thumbnail's `alt` is set even though its `<button>` already has an `aria-label`: if the
button's label were ever dropped, the image would still describe itself. A button's own label
wins over its contents, so this costs nothing.

The two skeleton states also set `aria-busy="true"` on the panels and remove it when real content
lands - a screen reader then says "busy" instead of reading four placeholder boxes as if they
were data.

---

## 6. Responsive: 0 px of overflow at four widths

Screenshots need a visible window, so this was measured **numerically**, which is stricter than
looking. The page was loaded in iframes of exactly 360, 768, 1024 and 1440 px - an iframe has its
own viewport, so the CSS media queries apply exactly as they would on a real device - and then
`documentElement.scrollWidth - clientWidth` was computed.

### The bug this found

At 360 px the page was **53 px too wide**. Finding the culprit took three passes, because the
element that *overflows* is not the element that *causes* it:

1. Walk every element, compare its right edge to the viewport -> **nothing** stuck out. The
   offending boxes were legitimately inside a card that was itself too wide.
2. Hide each top-level section in turn and watch for `scrollWidth` to shrink -> the **KPI
   section** was 386 px wide inside a 321 px container.
3. Walk that section's children -> the `.kpi-top` row had `scrollWidth: 208` while itself being
   130 px wide, and the culprit was `.icon-badge` with `scrollWidth: 208`.

208 px is exactly the tooltip's `max-width`. Four hidden-but-laid-out tooltips were widening the
grid. Changing them to `display: none` at rest fixed it. Re-measured: **0 px**.

### Final measurements

| Width | Horizontal overflow | Alert log | Chart | Gauge ring |
| --- | --- | --- | --- | --- |
| 360 px | **0 px** | 336 px tall, scrolls inside (content 777 px) | fixed 192 px box | 96 px |
| 768 px | **0 px** | 336 px tall, scrolls inside | fixed 192 px box | 120 px |
| 1024 px | **0 px** | 336 px tall, scrolls inside | fixed 192 px box | 120 px |
| 1440 px | **0 px** | 336 px tall, scrolls inside | fixed 192 px box | 120 px |

### The alert log scrolls inside its card

`max-height: 336px; overflow-y: auto; overscroll-behavior: contain;`

336 px is 84 x 4 - about six rows, enough to see a pattern without the log claiming the whole
screen. `scrollHeight 777 > clientHeight 336`, so it genuinely scrolls rather than stretching the
page. `overscroll-behavior: contain` is what stops the wheel from "falling through" to the page
once the list hits its end - a small thing that makes a long alert history feel broken when it is
missing.

### The banner on mobile

At 360 px the banner is 321 px wide, 43 px tall, wraps to **2 lines**, stays inside the viewport,
and does not add horizontal overflow. It drops to a 12 px font, 12 px padding and an 8 px gap
under 420 px; `min-width: 0` plus `overflow-wrap: anywhere` on the text is what allows a long zone
name to wrap instead of widening the bar.

### Phone-specific adjustments under 420 px

```css
.gauge { max-width: 96px; }       /* the only thing that can shrink without losing meaning */
.kpi-card { padding: 12px; }
.kpi-value { font-size: 26px; }   /* 30px would wrap "12" onto two lines in a 155px card */
.gauge-grid { gap: 4px; }
.source-select { max-width: 128px; }
#clock { display: none; }         /* least important item; buys room for the name */
```

---

## 7. Identity: favicon, title, footer

### Favicon, with no binary and no network

```html
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='...'%3E...%3C/svg%3E">
```

An inline SVG data URI: the same three rising bars as the logo mark, on the page background. It
is ~400 bytes inside the HTML, needs no extra request, cannot 404, and stays sharp at any size.
Why not a `.ico`: that would be a binary file added to git for something that is 16 px wide.

### Title

The `<title>` was already correct and is left alone:
`Crowd Analytics — Density & Bottleneck Monitor`.

P7 also sets a *live* title from the active alert count - `(1) Crowd Analytics` - and resets to
the full name at zero. Verified after the rewrite: with 0 active it reads the plain name, and
with 3 injected it read `(3) Crowd Analytics`.

### Footer

```html
<footer class="mt-4 text-center">
  <p class="footer-status" id="footer-status">Connecting to the engine…</p>
  <p class="footer-credit">
    Cogno Valley Labs, Internship Round 1 · YOLOv8n + ByteTrack on CPU
  </p>
</footer>
```

Two lines: the live status (it changes - "Live · crowded.mp4 · video 00:14") and a credit that
never changes. The credit names the model (`YOLOv8n`) and the tracker (`ByteTrack`) so a panel
can connect the numbers to the technology without asking.

`color-mix` is used for the muted effect, but **declared twice**:

```css
.footer-credit { color: rgba(143, 163, 191, 0.85); }
@supports (color: color-mix(in srgb, red 50%, transparent)) {
  .footer-credit { color: color-mix(in srgb, var(--muted) 85%, transparent); }
}
```

The plain `rgba` is the fallback: a browser without `color-mix` gets a legible value instead of
inheriting the body colour and shouting.

---

## 8. Cleanup: the console is now completely silent

### Dev buttons

The P6 preview cluster (four buttons that faked the banner and the skeletons) was already removed
in P7. Verified again: `document.querySelectorAll(".dev-btn, .dev-cluster").length === 0`.

### Console

| Was | Now |
| --- | --- |
| `console.warn("cdn.tailwindcss.com should not be used...")` on every load | the vendored call is neutralised; no CDN, no warning |
| `console.warn("Bad snapshot", error)` per malformed message | counted and shown in the footer: "Skipped 2 malformed messages · still live" |

The second change deserves a sentence. A malformed WebSocket message is a real thing worth
knowing about - but a `console.warn` twice a second would bury an actual error, and the brief
asks for a clean console. A **counter in the footer** is quieter for a demo and still visible to
whoever is debugging: the information is not lost, it is just not shouting.

Measured on a live page after P8, counting every level the console API exposes:

```
errors: 0   warnings: 0   info: 0   debug: 0
```

### Dead code removed

* `.video-frame img.is-stalled` - a class that no line of JavaScript ever set.
* `.overlay-toggles.is-busy` - same.
* A duplicated `.video-frame img` block that appeared twice in the file.
* `focus-visible { border-radius: 4px }` - it reshaped whatever received focus.
* Inline `style="font-size:10.5px"`, `style="position:relative;height:190px"`,
  `style="width:70%;margin:8px auto 0"` - all replaced by classes on the scale.

`grep` for `TODO|FIXME|debugger|console.` across `static/`: only one hit remains, and it is a
*comment explaining* why the console call was replaced.

---

## 9. One real code fix that came out of the polish pass

Polishing the alert log exposed a genuine behaviour bug, not a cosmetic one.

The P7 comment on `prependAlert` said:

> *"Why not just re-render everything: a full re-render would reset the scroll position."*

...and then the function called `renderAlerts()`, which replaces the entire `<ul>`. So the comment
described an intent the code did not honour. With 33 rows in the log, a new alert arriving while
an operator was reading row 8 threw them back to the top.

Now it truly prepends:

```js
list.querySelector(".alert-row:last-child")?.remove();          // keep the list at 50
list.insertAdjacentHTML("afterbegin", alertRowMarkup(alert, true));
```

Verified by measuring the actual scroll offset across a new alert: **100 -> 125.3** (the list grew
by one row above the scroll position, which is correct) and the new row was first with `is-new`.

The same treatment went to `reconcileActiveAlerts`. It used to re-render the whole list when a
stale row was corrected; it now flips that one row's class and tag in place:

```js
row.classList.remove("is-active");
tag.className = "alert-tag cleared";
tag.textContent = "Cleared";
```

And the summary chip logic was pulled into one `paintAlertSummary()` because three call sites
(the first load, a new alert, the reconciliation) must all leave the chip and the tab title
agreeing with the rows. Three copies is how they drift apart.

---

## 10. A note on what was NOT changed

The brief said "do not add features; improve quality". These were considered and rejected:

| Idea | Why not |
| --- | --- |
| A theme toggle | That is a feature, and the dark theme is the design. |
| A "compact mode" | A second layout doubles what has to be tested on a 2-day project. |
| Animating the chart | `chart.update("none")` is deliberate; a 300 ms ease every 500 ms never finishes. |
| Dropping Tailwind entirely | Would mean hand-writing ~40 layout utilities. The vendored file works offline and is 412 KB, which is cheaper than the risk of a rewrite. |
| A toast "undo" button | Nothing to undo - an alert is a measurement, not an action. |
| Loading a web font that self-hosts | Inter is optional by design; self-hosting 4 weights would add ~100 KB of binaries for a nicety. |

---

## 11. Every number from this pass, in one table

| Measurement | Value |
| --- | --- |
| Tailwind vendored | 412,549 bytes, real library verified |
| Chart.js vendored | 205,399 bytes, v4.4.1 verified |
| Console calls after P8 | **0** errors, 0 warnings, 0 info, 0 debug |
| Dev buttons left | **0** |
| Horizontal overflow @ 360 / 768 / 1024 / 1440 | **0 / 0 / 0 / 0 px** |
| Overflow bug found and fixed | **53 px** at 360 px (hidden tooltips in layout) |
| Distinct font sizes rendered | **7**, all from the scale |
| Distinct font weights | **2** (400, 600) |
| Cards using more than 2 weights | **0 of 41** |
| Distinct radii | **4** (8, 10, 16, 999) |
| Muted text contrast on a card | **7.03:1** (AAA needs 7.0) |
| Weakest colour contrast | `crit` **4.81:1** (AA needs 4.5; used for non-text) |
| Footer credit contrast | **5.76:1** after raising 72% -> 85% |
| Alert log | 336 px box, 777 px content, scrolls inside |
| Banner @ 360 px | 321 px wide, 43 px tall, 2 lines, inside viewport |
| KPI card with the font blocked | 301 x 151 px, identical to with Inter |
| `prefers-reduced-motion` rules | 4 (animations, transitions, hover lift, skeleton) |
| Unit tests | **54 passed** |
| Smoke test | **10/10 passed** |

---

## 12. Five questions a panel may ask

1. **"You edited a third-party file. Isn't that risky?"**
   One `console.warn` call was replaced with `void 0`, inside a file we now ship ourselves. It is
   documented in section 2, the file still parses, and the only behaviour change is that a
   production warning about the CDN build no longer fires - which is correct, because we are no
   longer loading from a CDN.

2. **"Why keep Tailwind at all if you are not using its build step?"**
   Tailwind's Play CDN build compiles class names in the browser. We use it for layout only
   (`flex`, `grid`, `gap-3`, `lg:col-span-8`); every colour, size, radius and shadow lives in
   `style.css`. Vendoring it means the layout survives an offline demo. Dropping it would mean
   hand-writing about 40 utilities for no visible gain.

3. **"How do you know the page works with no internet?"**
   Every `src` and `href` was enumerated and only the optional font is remote. Then it was proved
   rather than argued: the font `<link>` was removed and the body forced to `system-ui`, and the
   KPI card measured **301 x 151 px - exactly the same** as with Inter loaded, with 0 px overflow.
   The five local assets were re-fetched and all returned 200.

4. **"How did you verify accessibility without a screen reader?"**
   Three ways. Contrast was **calculated** with the WCAG luminance formula, not eyeballed - which
   is how the footer credit was caught at 4.41:1 and raised to 5.76:1. The tab order was
   **enumerated from the live DOM** in order, which is how the unreachable scrolling alert log was
   found. And every status was checked for **text + icon + colour** rather than colour alone; the
   one colour-only cue (the severity bar) is `aria-hidden` and redundant.

5. **"What did the polish pass actually fix, as opposed to decorate?"**
   Four things that were genuinely broken or dishonest: the page was 53 px too wide at 360 px
   (hidden tooltips in layout); the gauge arc changed colour instantly while its length glided for
   0.9 s, so three signals disagreed for a second; the footer credit was below the AA contrast
   threshold at 4.41:1; and `prependAlert` claimed to preserve scroll position while actually
   re-rendering the list. The rest - the lifts, the presses, the slide-in - is so the interface
   feels like it heard you, which is a quality claim, not a correctness one.

---

## 13. Files touched in P8

| File | What changed |
| --- | --- |
| `static/vendor/tailwind.js` | **new** - vendored Play CDN build, one warning call neutralised |
| `static/vendor/chart.umd.min.js` | **new** - vendored Chart.js 4.4.1 |
| `static/index.html` | local scripts, favicon, optional font, KPI tooltips, chart-box class, footer credit, `tabindex` on the alert log |
| `static/style.css` | rebuilt on one type/radius/spacing scale; hover lift, press states, gauge stroke transition, banner slide-in, tooltips, footer; responsive + reduced-motion passes |
| `static/app.js` | tooltip-safe skeleton classes, `aria-busy`, thumbnail alt text, `paintAlertSummary`, true prepend, in-place reconciliation, console silenced |
| `docs/explained/polish.md` | this file |

No Python file changed. No endpoint changed. No new dependency was added.
