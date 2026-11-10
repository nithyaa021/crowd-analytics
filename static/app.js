/* Crowd Analytics dashboard — live data client.
 *
 * This file replaces the P6 sample object with real data from the server. The render functions
 * are the same ones P6 wrote; what changes is where their input comes from:
 *
 *   /api/zones     -> the gauge list (zone names and capacities)
 *   /api/alerts    -> the alert log history
 *   /api/history   -> the first 120 chart points
 *   /api/sources   -> the clip dropdown
 *   /ws            -> one snapshot every 0.5 s: the KPI numbers, gauge counts, banner and
 *                     chart point
 *
 * Two shapes are worth keeping in mind, because everything below works with one or the other:
 *
 *   snapshot zone (from /ws):  { name, count, capacity, fill, status, over_for, avg_dwell, max_dwell }
 *   api zone (from /api/zones): { name, capacity, polygon }
 *
 * The snapshot is the live truth. /api/zones only tells us which zones exist and how big they
 * are, so the gauges can be drawn before the first message arrives.
 *
 * Vanilla JavaScript only. No framework, no build step, no icon library.
 */

"use strict";

/* ---------------------------------------------------------------------------
 * 1. Settings and state
 * ------------------------------------------------------------------------- */

/** How long a KPI number takes to travel to its new value, in milliseconds. */
const KPI_ANIM_MS = 300;

/** How many points the chart keeps. 120 points at 2 s each is four minutes of history. */
const CHART_MAX_POINTS = 120;

/** Reconnect backoff: start at 1 s, double it, never wait longer than 10 s. */
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 10000;

/** How long a toast stays on screen, and how long the new alert row keeps its flash. */
const TOAST_MS = 5000;
const FLASH_MS = 1600;

/** Fetch timeouts. A hung request must not leave a panel on a skeleton forever. */
const FETCH_TIMEOUT_MS = 8000;

/** Radius of the gauge ring in SVG units; the stroke math below depends on it. */
const GAUGE_RADIUS = 52;
/** Circumference of that ring: 2 * PI * 52 ≈ 326.73 SVG units. */
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS;

/** Colour per status, used for the gauge arc and the chart line of each zone. */
const STATUS_STROKE = { OK: "var(--ok)", NEAR: "var(--warn)", OVER: "var(--crit)" };
const ZONE_COLORS = ["#38bdf8", "#a78bfa", "#f472b6", "#34d399"];

/**
 * The dashboard's memory. Everything the screen needs that is not already in the DOM.
 *
 * Why one object instead of scattered variables: the WebSocket handler and the fetch handlers
 * both write here, and a single object makes it obvious what is shared between them.
 */
const app = {
  // Zone identity and capacity, from /api/zones: [{ name, capacity }]
  zoneDefs: [],
  // Per-zone stat lookup by name, filled from each snapshot: name -> snapshot zone
  latestZones: new Map(),
  // The alert rows currently on screen, newest first, in the API's shape
  alerts: [],
  // The chart series. Kept here rather than in Chart.js so a source switch can clear both.
  chart: { labels: [], total: [], perZone: {} },
  // Chart.js instance, so updates replace data instead of leaking a canvas context each time.
  chartInstance: null,
  // Current overlay flags: these become the /video query string.
  overlays: { boxes: true, zones: true, heat: false },
  // Whether the video element has been pointed at the stream yet.
  videoAttached: false,
  // Counts stream requests, so each one gets a distinct cache-busting value.
  videoRequest: 0,
  // WebSocket and reconnect bookkeeping.
  socket: null,
  reconnectDelay: RECONNECT_MIN_MS,
  reconnectTimer: null,
  // True once a socket has opened, so a later retry is shown as Reconnecting, not Connecting.
  hasConnected: false,
  // Set while a source switch is in progress, so snapshots do not repopulate a cleared chart.
  switching: false,
  // The clip the engine last reported playing, so a change can be detected from /ws alone.
  source: "",
  // The most recent snapshot, kept so the KPI row can be repainted after the fetches finish.
  lastSnapshot: null,
  // Counts WebSocket messages that could not be parsed, so a bad frame is visible but silent.
  badMessages: 0,
  // In-flight KPI animations, key -> { frame, timer }, so a new value can cancel the old one.
  kpiAnim: new Map(),
};

/* ---------------------------------------------------------------------------
 * 2. Small helpers
 * ------------------------------------------------------------------------- */

/**
 * Escapes text before it goes into an HTML template.
 *
 * Why: zone names come from zones.json, which a person edits by hand, and alert rows now come
 * from the network. A name containing "<" would otherwise inject markup into the page.
 *
 * Example: `Main & Co` becomes `Main &amp; Co`.
 *
 * @param {string} value - raw text.
 * @returns {string} the same text with HTML-significant characters replaced.
 */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * Maps a status word to the CSS class used by the chip and the gauge.
 *
 * Example: "OVER" -> "over", which matches .status-chip.over.
 *
 * @param {string} status - "OK", "NEAR" or "OVER".
 * @returns {string} the lowercase class name.
 */
function statusClass(status) {
  return String(status || "OK").toLowerCase();
}

/**
 * Returns a status-appropriate inline SVG icon.
 *
 * Why inline SVG: the brief forbids an icon library, and a three-line path is smaller than the
 * request that would fetch an icon font.
 *
 * @param {string} status - "OK", "NEAR" or "OVER".
 * @returns {string} an inline <svg> string safe to insert into HTML.
 */
function statusIcon(status) {
  if (status === "OVER") {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"
      stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle>
      <path d="M12 7v6"></path><path d="M12 17h.01"></path></svg>`;
  }
  if (status === "NEAR") {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 3 2 20h20L12 3z"></path><path d="M12 9v4"></path></svg>`;
  }
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5"></path></svg>`;
}

/**
 * Formats seconds as a compact dwell string.
 *
 * Example: 18.4 -> "18 s"; 6.2 -> "6.2 s".
 *
 * @param {number} seconds - dwell time in seconds.
 * @returns {string} the formatted value with its unit.
 */
function formatDwell(seconds) {
  const value = Number(seconds) || 0;
  return value >= 10 ? `${Math.round(value)} s` : `${value.toFixed(1)} s`;
}

/**
 * Turns video seconds into an mm:ss label for the chart's x axis.
 *
 * Why video time and not the wall clock: the chart must line up with what is on screen. At
 * video second 31.5 the spike in the line is the crowd you can see in the frame.
 *
 * Example: 31.5 -> "00:31"; 125.0 -> "02:05".
 *
 * @param {number} seconds - video time in seconds.
 * @returns {string} the mm:ss label.
 */
function videoLabel(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const secs = String(total % 60).padStart(2, "0");
  return `${minutes}:${secs}`;
}

/**
 * Turns an ISO-8601 timestamp into a short local time for the alert log.
 *
 * Why: the API stores UTC (`2026-11-10T09:03:21+00:00`) but an operator reads a wall clock.
 * Anything unparseable is passed through unchanged rather than showing "Invalid Date".
 *
 * Example: "2026-11-10T09:03:21+00:00" -> "14:33:21" in India (UTC+5:30).
 *
 * @param {string} iso - the stored timestamp.
 * @returns {string} HH:MM:SS in local time.
 */
function clockTime(iso) {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) {
    return String(iso || "").slice(11, 19) || "—";
  }
  return moment.toLocaleTimeString("en-GB", { hour12: false });
}

/**
 * Chooses a stable colour for a zone by its position in the zone list.
 *
 * Why stable: a zone keeps its colour for the whole session, so the legend and the line always
 * refer to the same thing.
 *
 * @param {number} index - position in app.zoneDefs.
 * @returns {string} a hex colour.
 */
function zoneColor(index) {
  return ZONE_COLORS[index % ZONE_COLORS.length];
}

/* ---------------------------------------------------------------------------
 * 3. Fetching, with a visible error state
 * ------------------------------------------------------------------------- */

/**
 * Fetches JSON with a timeout and a single, friendly error path.
 *
 * Why one wrapper: the brief requires every fetch to be wrapped in try/catch, and doing that
 * five times invites four slightly different behaviours. One function means one message style,
 * one timeout, and one place to fix a mistake.
 *
 * Example: getJson("/api/zones") resolves to an array; a 500 rejects with "Server said 500".
 *
 * @param {string} url - an absolute path on this server.
 * @returns {Promise<any>} the parsed JSON body.
 */
async function getJson(url) {
  // AbortSignal.timeout stops a hung socket from keeping the skeleton up forever.
  const response = await fetch(url, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) });
  if (!response.ok) {
    throw new Error(`Server said ${response.status} for ${url}`);
  }
  return response.json();
}

/**
 * Shows the inline error bar with a plain-English message.
 *
 * Why never window.alert: it blocks the page, including the video element, and cannot be styled
 * or dismissed politely. An inline bar keeps the dashboard usable while the message is read.
 *
 * @param {string} message - what went wrong, in the user's terms.
 * @param {Function|null} onRetry - called if the user presses Retry, or null to hide the button.
 */
function showError(message, onRetry = null) {
  const bar = document.getElementById("error-bar");
  document.getElementById("error-text").textContent = message;
  const retry = document.getElementById("error-retry");
  // Hiding rather than removing keeps the markup static and the handler simple.
  retry.hidden = !onRetry;
  retry.onclick = onRetry || null;
  bar.hidden = false;
}

/** Hides the inline error bar. Why a function: three call sites clear it. */
function clearError() {
  document.getElementById("error-bar").hidden = true;
}

/* ---------------------------------------------------------------------------
 * 4. KPI row
 * ------------------------------------------------------------------------- */

/**
 * Animated number writer for the KPI cards.
 *
 * Why animate at all: the WebSocket delivers a value twice a second, and a number that jumps
 * 8 -> 12 -> 9 -> 14 is hard to follow. A 300 ms count-up makes the direction of change visible.
 *
 * Why requestAnimationFrame and not setInterval: the browser aligns the frames with its own
 * paint, so the animation costs nothing when the tab is in the background.
 *
 * Why a setTimeout fallback: browsers stop firing requestAnimationFrame for a hidden tab. Without
 * a fallback the number would freeze halfway (say "7.3 s" forever) because the frames that would
 * have finished the animation never arrive. The timer always lands on the true value, so the
 * screen is correct even when the animation is skipped.
 *
 * @param {string} key - "people", "peak", "dwell" or "fps".
 * @param {number} target - the value to land on.
 * @param {string} [unit] - a small trailing unit, e.g. "s"; omit for none.
 */
function animateKpi(key, target, unit = "") {
  const node = document.querySelector(`[data-kpi="${key}"]`);
  if (!node) {
    return;
  }

  // Read the number currently on screen so a new message animates from where the eye left off.
  const from = Number(node.dataset.value || 0);
  const to = Number(target) || 0;
  node.dataset.value = String(to);

  // A text-only suffix is rendered smaller. Rebuilding it once per animation is cheaper than
  // tracking it separately, and it keeps the unit in the same place as the digits.
  const render = (value) => {
    const text = key === "dwell" ? value.toFixed(1) : String(Math.round(value));
    node.innerHTML = unit ? `${escapeHtml(text)}<span class="unit">${escapeHtml(unit)}</span>`
      : escapeHtml(text);
  };

  // A newer message supersedes the animation still running for this card.
  const running = app.kpiAnim.get(key);
  if (running) {
    cancelAnimationFrame(running.frame);
    clearTimeout(running.timer);
  }

  const reducedMotion = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // No change, no animation support, or the user asked for less motion: write and stop.
  if (from === to || typeof requestAnimationFrame !== "function" || reducedMotion) {
    render(to);
    app.kpiAnim.delete(key);
    return;
  }

  const started = performance.now();
  const step = (now) => {
    const progress = Math.min((now - started) / KPI_ANIM_MS, 1);
    // easeOutCubic: fast at the start, settling at the end, which reads as "arriving".
    const eased = 1 - (1 - progress) ** 3;
    if (progress < 1) {
      render(from + (to - from) * eased);
      const handle = app.kpiAnim.get(key);
      if (handle) {
        handle.frame = requestAnimationFrame(step);
      }
      return;
    }
    render(to);
    const handle = app.kpiAnim.get(key);
    if (handle) {
      clearTimeout(handle.timer);
    }
    app.kpiAnim.delete(key);
  };

  // The guarantee: whatever happens to the frames, the card shows the true value within a
  // fraction of a second of the animation window.
  const timer = setTimeout(() => {
    render(to);
    app.kpiAnim.delete(key);
  }, KPI_ANIM_MS + 60);

  app.kpiAnim.set(key, { frame: requestAnimationFrame(step), timer });
}

/**
 * Writes the four KPI cards and the header FPS chip from one snapshot.
 *
 * Why this is its own function: the KPI row is the first thing anyone reads, and it is the most
 * likely place for a "NaN" to appear if a field is missing. One function means one place to fix.
 *
 * @param {object} snapshot - one message from /ws.
 */
function renderKpis(snapshot) {
  const zones = snapshot.zones || [];
  const total = Number(snapshot.total_people) || 0;

  // The headline dwell is the busiest zone's, not the mean of the means: a quiet zone would
  // otherwise drag the number down and hide a real bottleneck.
  const busiest = zones.reduce(
    (worst, zone) => ((zone.avg_dwell || 0) > (worst.avg_dwell || 0) ? zone : worst),
    { avg_dwell: 0, name: "—" },
  );

  animateKpi("people", total);
  animateKpi("peak", Number(snapshot.peak_people) || 0);
  animateKpi("dwell", Number(busiest.avg_dwell) || 0, "s");
  animateKpi("fps", Number(snapshot.fps) || 0);

  document.querySelector('[data-kpi-caption="people"]').textContent =
    `${zones.length} zone${zones.length === 1 ? "" : "s"} monitored`;
  document.querySelector('[data-kpi-caption="dwell"]').textContent =
    busiest.name === "—" ? "no data yet" : `longest in ${busiest.name}`;

  // The header chip mirrors the KPI so the two can never disagree.
  document.getElementById("fps-chip").textContent = (Number(snapshot.fps) || 0).toFixed(1);
}

/* ---------------------------------------------------------------------------
 * 5. Zone gauges
 * ------------------------------------------------------------------------- */

/**
 * Draws one SVG ring per zone and returns the markup as a string.
 *
 * Why a string builder separate from the DOM write: update() calls this twice a second. Building
 * the markup and assigning it once keeps the gauge structure identical between frames, so the
 * CSS transition on stroke-dashoffset animates instead of restarting from nothing.
 *
 * @param {Map<string, object>} latest - zone name -> the newest snapshot zone.
 * @returns {string} the inner HTML for #zone-gauges.
 */
function gaugeMarkup(latest) {
  return app.zoneDefs
    .map((definition) => {
      // A zone with no snapshot yet (the first 0.5 s, or a clip that just changed) reads 0/…
      const live = latest.get(definition.name) || { count: 0, over_for: 0, avg_dwell: 0 };
      const count = Number(live.count) || 0;
      const capacity = Number(definition.capacity) || 0;
      const status = live.status || deriveStatus(count, capacity);

      // The snapshot's own fill ratio is preferred, because it is computed next to the status and
      // the two can never disagree. count/capacity is the fallback for the first half second.
      const rawFill = Number.isFinite(Number(live.fill)) && live.fill !== undefined
        ? Number(live.fill)
        : (capacity > 0 ? count / capacity : 0);
      // Clip at 1: an over-capacity zone cannot fill more than a full ring, and the OVER chip
      // already says the rest. Without the clip the dashoffset goes negative and the arc wraps
      // around from the start, which looks like an empty ring.
      const fraction = Math.min(Math.max(rawFill, 0), 1);
      const offset = GAUGE_CIRCUMFERENCE * (1 - fraction);
      const isHot = status === "OVER" ? " is-hot" : "";

      return `
        <div class="gauge-card${isHot}">
          <svg class="gauge" viewBox="0 0 120 120" role="img"
               aria-label="${escapeHtml(definition.name)}: ${count} of ${capacity} people, ${status}">
            <!-- Rotate -90 deg so the ring starts at 12 o'clock instead of 3 o'clock. -->
            <g transform="rotate(-90 60 60)">
              <circle class="gauge-track" cx="60" cy="60" r="${GAUGE_RADIUS}"
                      fill="none" stroke-width="9"></circle>
              <circle class="gauge-arc" cx="60" cy="60" r="${GAUGE_RADIUS}"
                      fill="none" stroke-width="9"
                      stroke="${STATUS_STROKE[status] || STATUS_STROKE.OK}"
                      stroke-dasharray="${GAUGE_CIRCUMFERENCE.toFixed(2)}"
                      stroke-dashoffset="${offset.toFixed(2)}"></circle>
            </g>
            <text class="gauge-num" x="60" y="58" text-anchor="middle">${count}</text>
            <text class="gauge-cap" x="60" y="76" text-anchor="middle">/ ${capacity}</text>
          </svg>
          <div class="gauge-name" title="${escapeHtml(definition.name)}">
            ${escapeHtml(definition.name)}
          </div>
          <span class="status-chip ${statusClass(status)}">
            ${statusIcon(status)}${escapeHtml(status)}
          </span>
          <div class="gauge-dwell">avg ${formatDwell(live.avg_dwell)}</div>
        </div>`;
    })
    .join("");
}

/**
 * Mirrors app/zones.py status_for, for the half second before a snapshot names a status.
 *
 * Why duplicate the rule: the gauges must render before the first message arrives, and the
 * capacity is already known. Keeping the thresholds identical means the placeholder and the
 * live state can never disagree.
 *
 * Example with capacity 10: 7 -> OK, 8 -> NEAR, 10 -> NEAR, 11 -> OVER.
 *
 * @param {number} count - people in the zone.
 * @param {number} capacity - the zone's capacity.
 * @returns {string} "OK", "NEAR" or "OVER".
 */
function deriveStatus(count, capacity) {
  if (capacity > 0 && count > capacity) {
    return "OVER";
  }
  // 0.8 is config.NEAR_RATIO on the server; see docs/explained/live.md for why it is repeated.
  if (capacity > 0 && count >= 0.8 * capacity) {
    return "NEAR";
  }
  return "OK";
}

/**
 * Writes the gauges and the summary chip into the page.
 *
 * @param {Map<string, object>} latest - zone name -> the newest snapshot zone.
 */
function renderGauges(latest) {
  const container = document.getElementById("zone-gauges");
  const summary = document.getElementById("zones-summary");

  if (!app.zoneDefs.length) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path>
          <path d="M12 16h.01"></path>
        </svg>
        <span>No zones for this clip.</span>
      </div>`;
    summary.textContent = "none";
    summary.style.color = "var(--muted)";
    return;
  }

  container.innerHTML = gaugeMarkup(latest);
  // Real content has arrived, so the panel is no longer waiting for a shape to replace.
  container.removeAttribute("aria-busy");

  // Summary chip: how many zones are over, which is the single number worth reading at a glance.
  const overCount = app.zoneDefs.filter((definition) => {
    const live = latest.get(definition.name);
    const status = live && live.status
      ? live.status
      : deriveStatus(live ? live.count : 0, definition.capacity);
    return status === "OVER";
  }).length;
  summary.textContent = overCount > 0 ? `${overCount}/${app.zoneDefs.length} over` : "all normal";
  summary.style.color = overCount > 0 ? "var(--crit)" : "var(--ok)";
}

/* ---------------------------------------------------------------------------
 * 6. Alert log
 * ------------------------------------------------------------------------- */

/**
 * Normalises one alert from the API or from a snapshot into the row shape the renderer wants.
 *
 * Why normalise: GET /api/alerts returns database columns (`started_at`, `peak_count`, `ended_at`)
 * while a new alert on the socket is `{ id, zone, keyframe }`. One function turns both into
 * `{ id, zone, startedAt, peak, capacity, active, keyframe }`, so the renderer never branches.
 *
 * Example: { peak_count: 8, capacity: 4, ended_at: null } -> { peak: 8, capacity: 4, active: true }.
 *
 * @param {object} raw - an alert in either shape.
 * @returns {object} the row shape.
 */
function normaliseAlert(raw) {
  return {
    id: Number(raw.id) || 0,
    zone: String(raw.zone || "Unknown"),
    startedAt: clockTime(raw.startedAt || raw.started_at),
    peak: Number(raw.peak ?? raw.peak_count) || 0,
    capacity: Number(raw.capacity) || 0,
    // An alert is active while it has no ended_at. A socket alert is brand new, so also active.
    active: raw.active !== undefined ? Boolean(raw.active) : !raw.ended_at,
    keyframe: raw.keyframe || null,
  };
}

/**
 * Builds one alert row's markup.
 *
 * @param {object} alert - a normalised alert.
 * @param {boolean} isNew - true to add the flash class.
 * @returns {string} the <li> markup.
 */
function alertRowMarkup(alert, isNew) {
  // Severity is derived, not stored: a peak far above capacity is critical, a marginal
  // overshoot is a warning. Deriving it keeps one source of truth for the colour.
  const ratio = alert.capacity > 0 ? alert.peak / alert.capacity : 0;
  const severity = alert.active ? "crit" : ratio >= 1.3 ? "crit" : "warn";
  const tagClass = alert.active ? "active" : "cleared";
  const tagText = alert.active ? "Active" : "Cleared";

  // A real thumbnail when there is a keyframe, a placeholder frame otherwise. Only a real photo
  // becomes a button: opening a modal on an empty placeholder would waste the click.
  //
  // Why the <img> carries alt text even though the button already has an aria-label: if the
  // button's label were ever dropped, the image would still describe itself. The aria-label
  // stays the accessible name because a button's own label wins over its contents.
  const thumb = alert.keyframe
    ? `<button type="button" class="alert-thumb is-clickable" data-alert-id="${alert.id}"
              data-keyframe="${escapeHtml(alert.keyframe)}"
              aria-label="Open evidence for ${escapeHtml(alert.zone)}">
         <img src="${escapeHtml(alert.keyframe)}"
              alt="Snapshot of ${escapeHtml(alert.zone)} at ${escapeHtml(alert.startedAt)}">
       </button>`
    : `<span class="alert-thumb">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
           <rect x="3" y="4" width="18" height="16" rx="2"></rect>
           <circle cx="9" cy="10" r="1.6"></circle>
           <path d="m4 18 5-5 4 4 3-3 4 4"></path>
         </svg>
       </span>`;

  return `
    <li class="alert-row${alert.active ? " is-active" : ""}${isNew ? " is-new" : ""}"
        data-alert-id="${alert.id}">
      <span class="alert-sev ${severity}" aria-hidden="true"></span>
      ${thumb}
      <span class="alert-main">
        <span class="alert-top">
          <span class="alert-time">${escapeHtml(alert.startedAt)}</span>
          <span class="alert-zone">${escapeHtml(alert.zone)}</span>
        </span>
        <span class="alert-meta">peak ${alert.peak}/${alert.capacity}</span>
      </span>
      <span class="alert-tag ${tagClass}">${tagText}</span>
    </li>`;
}

/**
 * Sets the browser tab's title to the active alert count.
 *
 * Why the tab title: an operator may have the dashboard in a background tab while working
 * elsewhere, and the count in the title is the only signal that reaches them there.
 *
 * Example: 1 active -> "(1) Crowd Analytics"; 0 active -> the plain product name.
 *
 * @param {number} activeCount - alerts currently firing.
 */
function updateTitle(activeCount) {
  document.title = activeCount > 0
    ? `(${activeCount}) Crowd Analytics`
    : "Crowd Analytics — Density & Bottleneck Monitor";
}

/**
 * Writes the alert log's summary chip and the browser tab title.
 *
 * Why one function: three places change the list (the first load, a new alert, the live
 * reconciliation) and all three must leave the same two indicators agreeing with the rows.
 *
 * Example: 2 active of 30 rows -> chip "2 active / 30", title "(2) Crowd Analytics".
 *
 * @param {object[]} alerts - normalised alerts currently on screen.
 */
function paintAlertSummary(alerts) {
  const summary = document.getElementById("alerts-summary");
  const activeCount = alerts.filter((alert) => alert.active).length;
  summary.textContent = alerts.length
    ? `${activeCount} active / ${alerts.length}`
    : "0";
  summary.style.color = activeCount > 0 ? "var(--crit)" : "var(--ok)";
  updateTitle(activeCount);
}

/**
 * Writes the alert log, or the empty state when there is nothing to show.
 *
 * Why the empty state matters: an empty list looks identical to a broken panel. "No alerts. All
 * zones normal." tells the operator the difference in three words.
 *
 * @param {object[]} alerts - normalised alerts, newest first.
 * @param {number} newId - the id to flash, or 0 for none.
 */
function renderAlerts(alerts, newId = 0) {
  const list = document.getElementById("alert-list");

  if (!alerts.length) {
    list.innerHTML = `
      <li class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M20 6 9 17l-5-5"></path>
        </svg>
        <span>No alerts. All zones normal.</span>
      </li>`;
    list.removeAttribute("aria-busy");
    paintAlertSummary(alerts);
    return;
  }

  list.innerHTML = alerts.map((alert) => alertRowMarkup(alert, alert.id === newId)).join("");
  list.removeAttribute("aria-busy");
  paintAlertSummary(alerts);
}

/**
 * Adds one brand-new alert at the top of the log and flashes it.
 *
 * Why not just re-render everything: a full re-render would reset the scroll position and the
 * flash would land on every row at once. Prepending one <li> keeps the rest of the list still.
 *
 * @param {object} rawAlert - { id, zone, keyframe } from the snapshot.
 * @param {object} [context] - optional { count, capacity } from the snapshot for the first paint.
 */
function prependAlert(rawAlert, context = {}) {
  const alert = normaliseAlert({
    ...rawAlert,
    peak: context.count ?? rawAlert.peak,
    capacity: context.capacity ?? rawAlert.capacity,
    active: true,
  });

  // A duplicate id would mean the same alert counted twice; ignore it.
  if (app.alerts.some((existing) => existing.id === alert.id)) {
    return;
  }

  app.alerts.unshift(alert);
  // The log shows the newest 50; anything past that is still in the database.
  app.alerts = app.alerts.slice(0, 50);

  const list = document.getElementById("alert-list");

  // The skeleton or empty state has no rows to preserve, so the first real alert builds the list.
  if (list.querySelector(".empty-state") || !list.querySelector(".alert-row")) {
    renderAlerts(app.alerts, alert.id);
    return;
  }

  // Otherwise insert one row at the top. Why not renderAlerts() here: that replaces the whole
  // list, which throws away the scroll position - and an operator reading row 12 should not be
  // sent back to row 1 because a new alert arrived. Drop the last row to keep the list at 50.
  list.querySelector(".alert-row:last-child")?.remove();
  list.insertAdjacentHTML("afterbegin", alertRowMarkup(alert, true));
  list.removeAttribute("aria-busy");
  paintAlertSummary(app.alerts);
}

/* ---------------------------------------------------------------------------
 * 7. Chart
 * ------------------------------------------------------------------------- */

/**
 * Creates the Chart.js instance once, with one dataset per zone plus the total and capacity.
 *
 * Why build the datasets from app.zoneDefs: the number of zones comes from /api/zones, so the
 * chart cannot hard-code "two lines" for a clip that defines three.
 *
 * @returns {object} the Chart instance.
 */
function createChart() {
  const canvas = document.getElementById("headcount-chart");
  const context = canvas.getContext("2d");

  // A vertical gradient makes the fill read as "volume" rather than a flat block of colour.
  const gradient = context.createLinearGradient(0, 0, 0, 190);
  gradient.addColorStop(0, "rgba(56, 189, 248, 0.34)");
  gradient.addColorStop(1, "rgba(56, 189, 248, 0.02)");

  const zoneDatasets = app.zoneDefs.map((definition, index) => ({
    label: definition.name,
    data: [],
    borderColor: zoneColor(index),
    backgroundColor: "transparent",
    borderWidth: 1.5,
    fill: false,
    tension: 0.35,
    pointRadius: 0,
    pointHoverRadius: 3,
  }));

  const config = {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Total",
          data: [],
          borderColor: "#38bdf8",
          backgroundColor: gradient,
          borderWidth: 2,
          fill: true,
          tension: 0.35,
          // No dots: 120 of them would look like a scatter plot, not a trend.
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: "#38bdf8",
        },
        ...zoneDatasets,
        {
          label: "Capacity",
          data: [],
          borderColor: "#ef4444",
          borderWidth: 1.5,
          borderDash: [5, 4],
          fill: false,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // The legend is written in HTML in the card header, so Chart.js's own one is redundant.
      plugins: { legend: { display: false }, tooltip: { intersect: false, mode: "index" } },
      interaction: { intersect: false, mode: "index" },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.04)", drawTicks: false },
          border: { display: false },
          ticks: {
            color: "#8fa3bf",
            font: { size: 10 },
            maxTicksLimit: 6,
            maxRotation: 0,
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255,255,255,0.05)", drawTicks: false },
          border: { display: false },
          ticks: { color: "#8fa3bf", font: { size: 10 }, precision: 0, maxTicksLimit: 5 },
        },
      },
    },
  };

  return new Chart(context, config);
}

/**
 * Pushes the current series in app.chart into the Chart.js instance.
 *
 * Why update("none"): the brief asks for it, and it is right - the chart repaints without an
 * animation, so a point arriving every half second does not produce an endless 300 ms ease that
 * the data keeps outrunning.
 */
function pushChartData() {
  const chart = app.chartInstance;
  if (!chart) {
    return;
  }

  chart.data.labels = app.chart.labels;
  chart.data.datasets[0].data = app.chart.total;
  app.zoneDefs.forEach((definition, index) => {
    // Dataset 0 is Total and the last one is Capacity, so zone i lives at i + 1.
    const series = app.chart.perZone[definition.name] || [];
    chart.data.datasets[index + 1].data = series;
  });

  // The capacity line follows the busiest zone's capacity, so "above the line" always means
  // "over capacity" for the zone that is closest to it.
  const capacity = app.zoneDefs.reduce(
    (max, definition) => Math.max(max, Number(definition.capacity) || 0),
    0,
  );
  const last = chart.data.datasets.length - 1;
  chart.data.datasets[last].data = app.chart.labels.map(() => capacity);

  chart.update("none");
}

/**
 * Appends one sample to every series, trimming to CHART_MAX_POINTS.
 *
 * Why trim from the front: the chart is a moving window. Keeping every point forever would grow
 * the array for the whole session and slowly make the browser work harder.
 *
 * @param {string} label - the mm:ss video time.
 * @param {number} total - people in frame.
 * @param {Map<string, object>} latest - zone name -> snapshot zone.
 */
function appendChartPoint(label, total, latest) {
  app.chart.labels.push(label);
  app.chart.total.push(total);
  app.zoneDefs.forEach((definition) => {
    const live = latest.get(definition.name);
    if (!app.chart.perZone[definition.name]) {
      app.chart.perZone[definition.name] = [];
    }
    app.chart.perZone[definition.name].push(live ? Number(live.count) || 0 : 0);
  });

  const overflow = app.chart.labels.length - CHART_MAX_POINTS;
  if (overflow > 0) {
    app.chart.labels.splice(0, overflow);
    app.chart.total.splice(0, overflow);
    Object.values(app.chart.perZone).forEach((series) => series.splice(0, overflow));
  }

  pushChartData();
  document.getElementById("chart-window").textContent =
    `last ${app.chart.labels.length} samples · video time`;
}

/**
 * Prefills the chart from GET /api/history.
 *
 * Why: a page opened in the middle of a demo should show the last few minutes, not an empty box
 * that fills up one point every two seconds. The history endpoint stores wall-clock timestamps,
 * so the labels are derived from them rather than from video time.
 *
 * @param {object[]} rows - [{ ts, zone, count }] oldest first, including the "ALL" total rows.
 */
function prefillChart(rows) {
  // One "ALL" row per sample time is the total; the per-zone rows share those timestamps.
  const byTime = new Map();
  rows.forEach((row) => {
    const key = row.ts;
    if (!byTime.has(key)) {
      byTime.set(key, { label: clockTime(key).slice(0, 5), total: 0, zones: {} });
    }
    const point = byTime.get(key);
    if (row.zone === "ALL") {
      point.total = Number(row.count) || 0;
    } else {
      point.zones[row.zone] = Number(row.count) || 0;
    }
  });

  const times = [...byTime.keys()].slice(-CHART_MAX_POINTS);
  app.chart = { labels: [], total: [], perZone: {} };
  app.zoneDefs.forEach((definition) => {
    app.chart.perZone[definition.name] = [];
  });

  times.forEach((key) => {
    const point = byTime.get(key);
    app.chart.labels.push(point.label);
    app.chart.total.push(point.total);
    app.zoneDefs.forEach((definition) => {
      app.chart.perZone[definition.name].push(point.zones[definition.name] || 0);
    });
  });

  pushChartData();
  document.getElementById("chart-window").textContent =
    app.chart.labels.length
      ? `last ${app.chart.labels.length} samples`
      : "waiting for the first samples";
}

/**
 * Rebuilds the chart's datasets, used after the zone list changes with a new clip.
 *
 * Why rebuild and not update: a different clip can have a different number of zones, and Chart.js
 * datasets are created by position. Recreating the instance is the simple, correct option; it
 * happens once per source switch, not once per message.
 */
function rebuildChart() {
  if (app.chartInstance) {
    app.chartInstance.destroy();
    app.chartInstance = null;
  }
  app.chartInstance = createChart();
  paintLegend();
}

/**
 * Writes the zone swatches into the HTML legend.
 *
 * Why HTML and not Chart.js's legend: the card header already holds the "Total" and "Capacity"
 * swatches, and one legend in one style is easier to read than two legends.
 */
function paintLegend() {
  const legend = document.getElementById("chart-legend");
  // One key is one 16 px swatch plus a word. Rebuilt from app.zoneDefs so a clip with two
  // zones gets two swatches without any change here.
  const key = (color, label) => `
    <span class="inline-flex items-center gap-2">
      <span class="legend-swatch" style="background:${color}"></span>
      ${label}
    </span>`;

  const fixed = key("var(--accent)", "Total");
  const zones = app.zoneDefs
    .map((definition, index) => key(zoneColor(index), escapeHtml(definition.name)))
    .join("");
  const capacity = key(
    "repeating-linear-gradient(90deg,var(--crit) 0 4px,transparent 4px 7px)",
    "Capacity",
  );
  legend.innerHTML = fixed + zones + capacity;
}

/* ---------------------------------------------------------------------------
 * 8. Banner, video, overlays
 * ------------------------------------------------------------------------- */

/**
 * Shows or hides the congestion banner.
 *
 * Why the text is assembled here rather than in the HTML: the banner serves any zone, and the
 * count and duration change twice a second.
 *
 * @param {object|null} problem - the worst congested zone, or null to hide the banner.
 */
function renderBanner(problem) {
  const banner = document.getElementById("congestion-banner");
  const text = document.getElementById("banner-text");

  if (!problem) {
    banner.hidden = true;
    return;
  }

  text.innerHTML =
    `CONGESTION: ${escapeHtml(problem.name)} ${problem.count}/${problem.capacity} ` +
    `<span class="banner-count">for ${Math.round(problem.over_for || 0)} s</span>`;
  banner.hidden = false;
}

/**
 * Finds the zone that has been over capacity the longest, for the banner.
 *
 * @param {object[]} zones - snapshot zones with over_for in seconds.
 * @returns {object|null} the worst zone, or null when nothing is over.
 */
function worstZone(zones) {
  const over = zones.filter((zone) => zone.status === "OVER");
  if (!over.length) {
    return null;
  }
  return over.reduce((worst, zone) =>
    ((zone.over_for || 0) > (worst.over_for || 0) ? zone : worst));
}

/**
 * Builds the MJPEG URL from the current overlay flags.
 *
 * Why rebuild on every toggle instead of using CSS: the overlays are drawn by OpenCV on the
 * server, so the flags have to travel in the request. The query string is the whole contract:
 * 1 turns an overlay on, 0 turns it off.
 *
 * Example: { boxes: true, zones: true, heat: false } -> "/video?boxes=1&zones=1&heat=0".
 *
 * @returns {string} the stream URL.
 */
function videoUrl() {
  const flags = app.overlays;
  return `/video?boxes=${flags.boxes ? 1 : 0}` +
    `&zones=${flags.zones ? 1 : 0}&heat=${flags.heat ? 1 : 0}`;
}

/**
 * Points the <img> at the stream, or reloads it after a flag change.
 *
 * Why a cache-busting parameter: the browser keeps the previous src as the image's current
 * state, and some browsers reuse it instead of opening a second connection, which would leave
 * the old overlay on screen. A changing query string guarantees a fresh request.
 *
 * Why a counter and not Date.now(): two toggles in the same millisecond would produce the same
 * URL, and the browser would quietly do nothing. A counter can never repeat.
 */
function attachVideo() {
  const image = document.getElementById("video");
  app.videoRequest += 1;
  image.src = `${videoUrl()}&t=${app.videoRequest}`;
  app.videoAttached = true;
  document.getElementById("video-idle").hidden = true;
}

/**
 * Wires the overlay chips: flip one flag, then reload the stream.
 *
 * Why aria-pressed is the only stored truth: the CSS colours the chip from that attribute, so the
 * visual state and what a screen reader announces can never drift apart.
 *
 * @param {string} id - the button's element id.
 * @param {string} key - the key in app.overlays.
 */
function bindToggle(id, key) {
  const button = document.getElementById(id);
  button.addEventListener("click", () => {
    app.overlays[key] = !app.overlays[key];
    button.setAttribute("aria-pressed", String(app.overlays[key]));
    // Only reload a stream that is running: before the first attach there is nothing to reload.
    if (app.videoAttached) {
      attachVideo();
    }
  });
  button.setAttribute("aria-pressed", String(app.overlays[key]));
}

/**
 * Sends the video container to fullscreen, and back again.
 *
 * Why the container and not the <img>: the overlay chips and their backdrop must stay visible in
 * fullscreen, and they are siblings of the image.
 */
function bindFullscreen() {
  const frame = document.querySelector(".video-frame");
  document.getElementById("fullscreen").addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (frame.requestFullscreen) {
      frame.requestFullscreen();
    }
  });
}

/* ---------------------------------------------------------------------------
 * 9. WebSocket with exponential backoff
 * ------------------------------------------------------------------------- */

/**
 * Reflects the connection state in the LIVE pill.
 *
 * Why words and colour together: colour alone fails for a colour-blind operator, and the pill is
 * the only indication that the numbers on screen are still moving.
 *
 * @param {"live"|"reconnecting"|"waiting"} state - the new pill state.
 */
function setLiveState(state) {
  const pill = document.getElementById("live-pill");
  const label = document.getElementById("live-label");
  pill.classList.remove("is-live", "is-reconnecting", "is-waiting");
  pill.classList.add(`is-${state}`);
  label.textContent = {
    live: "Connected",
    reconnecting: "Reconnecting",
    waiting: "Connecting",
  }[state] || "Connecting";
}

/**
 * Opens the WebSocket and keeps it open.
 *
 * Why reconnection lives here and not in a library: a dashboard in front of a panel must survive
 * the server restarting. The backoff starts at 1 s, doubles on each failure, and stops at 10 s,
 * so a server that is restarting for 40 s is still picked up within 10 s of coming back.
 *
 * Why reset the delay on a successful open and not on the first message: open is the moment the
 * connection is real; waiting for a message would keep the delay high after a fast recovery.
 */
function connectSocket() {
  // The page may be served over https, where ws:// is blocked; match the page's scheme.
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws`);
  app.socket = socket;
  // "Connecting" is only honest before the first successful open. After that, a retry is a
  // reconnection, and showing a third label for half a second just makes the pill flicker.
  if (!app.hasConnected) {
    setLiveState("waiting");
  }

  socket.addEventListener("open", () => {
    app.reconnectDelay = RECONNECT_MIN_MS;
    app.hasConnected = true;
    setLiveState("live");
    clearError();
  });

  socket.addEventListener("message", (event) => {
    try {
      update(JSON.parse(event.data));
    } catch (error) {
      // A malformed message must not kill the socket; the next one is probably fine.
      //
      // Why this is counted instead of console.warn'd: the brief asks for a console with no
      // noise, and a warning twice a second would bury a real error. A count shown in the
      // footer is quieter for the demo and still visible to whoever is debugging.
      app.badMessages += 1;
      document.getElementById("footer-status").textContent =
        `Skipped ${app.badMessages} malformed message${app.badMessages === 1 ? "" : "s"} · still live`;
    }
  });

  socket.addEventListener("close", () => {
    setLiveState("reconnecting");
    scheduleReconnect();
  });

  // "error" is always followed by "close", so the retry is scheduled in one place only.
  socket.addEventListener("error", () => {
    socket.close();
  });
}

/**
 * Waits for the backoff delay, then reconnects.
 *
 * Why a timer id: a second close event would otherwise queue a second socket, and two sockets
 * would double every render.
 */
function scheduleReconnect() {
  if (app.reconnectTimer) {
    return;
  }
  const delay = app.reconnectDelay;
  document.getElementById("footer-status").textContent =
    `Connection lost. Retrying in ${Math.round(delay / 1000)} s…`;
  app.reconnectTimer = setTimeout(() => {
    app.reconnectTimer = null;
    // Double for next time, capped. 1 s -> 2 -> 4 -> 8 -> 10 -> 10 ...
    app.reconnectDelay = Math.min(app.reconnectDelay * 2, RECONNECT_MAX_MS);
    connectSocket();
  }, delay);
}

/* ---------------------------------------------------------------------------
 * 10. The update path: one snapshot to the whole screen
 * ------------------------------------------------------------------------- */

/**
 * Corrects the "Active" tag on rows that the database still thinks are open.
 *
 * Why this is needed: an alert row is closed by the engine, but a crashed run leaves rows with
 * ended_at NULL forever. Marking one of those "Active" while the live banner says nothing is over
 * is the one thing an operator must not see - it makes both indicators untrustworthy.
 *
 * Why the zone's over_for and not its status: over_for is 0.0 exactly when the zone is not
 * currently over capacity, so it is the engine's own answer to "is this alert still firing?".
 *
 * Example: row 21 is open and its zone reports over_for 0 -> the row is shown as Cleared.
 *
 * @param {Map<string, object>} latest - zone name -> newest snapshot zone.
 */
function reconcileActiveAlerts(latest) {
  let changed = false;
  const list = document.getElementById("alert-list");

  app.alerts = app.alerts.map((alert) => {
    if (!alert.active) {
      return alert;
    }
    const zone = latest.get(alert.zone);
    if (!zone || (Number(zone.over_for) || 0) > 0) {
      return alert;
    }

    changed = true;
    // Flip the existing row in place instead of re-rendering the list. Why: a re-render resets
    // the scroll position, and this fires while an operator may be reading further down.
    const row = list.querySelector(`.alert-row[data-alert-id="${alert.id}"]`);
    if (row) {
      row.classList.remove("is-active");
      const tag = row.querySelector(".alert-tag");
      tag.className = "alert-tag cleared";
      tag.textContent = "Cleared";
    }
    return { ...alert, active: false };
  });

  if (changed) {
    paintAlertSummary(app.alerts);
  }
}

/**
 * Applies one WebSocket snapshot to every panel.
 *
 * Why one function for the whole screen: if each panel read its own data, the banner could
 * describe 10.5 s while the chart's last point is 10.0 s. One snapshot, one instant.
 *
 * @param {object} snapshot - one message from /ws.
 */
function update(snapshot) {
  // The engine may still be starting; an empty zone list means "nothing to say yet".
  const zones = Array.isArray(snapshot.zones) ? snapshot.zones : [];
  app.latestZones = new Map(zones.map((zone) => [zone.name, zone]));
  app.lastSnapshot = snapshot;

  // An empty zone list means the engine has no clip loaded yet. Rendering it would blank the
  // gauges and the KPI cards, so wait for a snapshot that carries real zones.
  if (!zones.length && !app.zoneDefs.length) {
    document.getElementById("footer-status").textContent = "Engine starting…";
    return;
  }

  // A clip change made in another tab arrives through the snapshot alone.
  if (snapshot.source && app.source && snapshot.source !== app.source && !app.switching) {
    app.source = snapshot.source;
    document.getElementById("video-source-chip").textContent = snapshot.source;
    document.getElementById("source-select").value = snapshot.source;
  } else if (snapshot.source) {
    app.source = snapshot.source;
  }

  renderKpis(snapshot);
  renderGauges(app.latestZones);

  // The banner is driven by alerts_active, per the brief, and names the worst over-capacity
  // zone when one exists. A cleared-alert frame hides it even if a zone is still near capacity.
  if (Number(snapshot.alerts_active) > 0) {
    renderBanner(worstZone(zones) || (zones.find((zone) => zone.status === "OVER") || null));
  } else {
    renderBanner(null);
  }

  // A source switch clears the chart; do not immediately refill it with the new clip's point
  // until the re-fetch has happened, or the chart would show one stale point and a gap.
  if (!app.switching && zones.length) {
    appendChartPoint(videoLabel(snapshot.ts), Number(snapshot.total_people) || 0,
      app.latestZones);
  }

  if (snapshot.new_alert) {
    const alert = snapshot.new_alert;
    const zone = zones.find((item) => item.name === alert.zone);
    prependAlert(alert, {
      count: zone ? zone.count : alert.count,
      capacity: zone ? zone.capacity : alert.capacity,
    });
    showToast(alert.zone, zone);
  } else {
    // Only reconcile when no alert is being added, so the new row's Active tag is never
    // immediately rewritten by a snapshot taken before the alert fired.
    reconcileActiveAlerts(app.latestZones);
  }

  document.getElementById("footer-status").textContent =
    `Live · ${snapshot.source || "—"} · video ${videoLabel(snapshot.ts)}`;
}

/* ---------------------------------------------------------------------------
 * 11. Toast and evidence modal
 * ------------------------------------------------------------------------- */

/**
 * Announces a brand-new alert in the corner of the screen.
 *
 * Why a toast as well as the log row: the alert log is in the right-hand column, and an operator
 * watching the video may not look there. The toast is the one element that appears where the eye
 * already is.
 *
 * @param {string} zoneName - the zone that went over capacity.
 * @param {object} [zone] - the snapshot zone, for the count and capacity.
 */
function showToast(zoneName, zone) {
  const stack = document.getElementById("toast-stack");
  const toast = document.createElement("div");
  toast.className = "toast";
  const detail = zone ? ` ${zone.count}/${zone.capacity} people` : "";
  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"
           stroke-linecap="round" aria-hidden="true">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
        <path d="M12 9v4"></path><path d="M12 17h.01"></path>
      </svg>
    </span>
    <span class="toast-body">
      <span class="toast-title">Over capacity</span>
      <span class="toast-text">${escapeHtml(zoneName)}${escapeHtml(detail)}</span>
    </span>`;
  stack.appendChild(toast);

  // Fade out, then remove. Removing without the fade would make the toast vanish mid-read.
  setTimeout(() => {
    toast.classList.add("is-leaving");
    setTimeout(() => toast.remove(), 220);
  }, TOAST_MS);
}

/**
 * Opens the evidence modal for one alert and loads its keyframe.
 *
 * Why the modal exists: the alert row is 38 px tall, and a panel question is usually "what did
 * the camera actually see?". The full photo is the answer, and it lives one click away.
 *
 * @param {object} alert - the normalised alert whose photo to show.
 */
function openEvidence(alert) {
  const modal = document.getElementById("evidence-modal");
  const image = document.getElementById("evidence-image");
  const empty = document.getElementById("evidence-empty");

  document.getElementById("evidence-title").textContent =
    `${alert.zone} · ${alert.startedAt}`;
  document.getElementById("evidence-meta").textContent =
    `peak ${alert.peak}/${alert.capacity} · ${alert.active ? "still active" : "cleared"}`;

  if (alert.keyframe) {
    image.src = alert.keyframe;
    image.hidden = false;
    image.alt = `Snapshot of ${alert.zone} at ${alert.startedAt}`;
    empty.hidden = true;
  } else {
    // Dropping the src stops the browser from keeping the previous photo on screen.
    image.removeAttribute("src");
    image.hidden = true;
    empty.hidden = false;
  }

  modal.showModal();
}

/**
 * Wires the alert list's one delegated click handler and the modal's close controls.
 *
 * Why delegation: rows are replaced on every new alert, so per-row listeners would be created
 * and thrown away twice a second. One listener on the parent survives every re-render.
 */
function bindAlertList() {
  document.getElementById("alert-list").addEventListener("click", (event) => {
    const button = event.target.closest(".alert-thumb.is-clickable");
    if (!button) {
      return;
    }
    const id = Number(button.dataset.alertId);
    const alert = app.alerts.find((item) => item.id === id);
    if (alert) {
      openEvidence(alert);
    }
  });

  const modal = document.getElementById("evidence-modal");
  document.getElementById("evidence-close").addEventListener("click", () => modal.close());
  // A click on the backdrop lands on the <dialog> itself, which is the natural "click outside".
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      modal.close();
    }
  });
}

/* ---------------------------------------------------------------------------
 * 12. Source switching
 * ------------------------------------------------------------------------- */

/**
 * Switches the engine to another clip, then rebuilds everything that depends on the clip.
 *
 * Why the order matters: POST first, so the engine starts seeking; then clear the chart, because
 * the old clip's numbers are meaningless now; then re-fetch zones, because a new clip has its own
 * polygons and capacities. Snapshots keep arriving throughout and are ignored for the chart while
 * `switching` is true.
 *
 * @param {string} name - a clip file name that /api/sources listed.
 */
async function changeSource(name) {
  const frame = document.querySelector(".video-frame");
  const label = document.getElementById("video-loading-label");
  const select = document.getElementById("source-select");

  app.switching = true;
  select.disabled = true;
  frame.classList.add("is-loading");
  if (label) {
    label.hidden = false;
  }

  try {
    const response = await fetch("/api/source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      // The API explains a bad name in its detail field; fall back to the status code.
      let detail = `Server said ${response.status}`;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (error) {
        // A non-JSON error body is not worth a second failure; the status code is enough.
      }
      throw new Error(detail);
    }

    // The new clip's zones and capacities.
    app.zoneDefs = await loadZones(name);
    app.latestZones = new Map();
    app.source = name;
    document.getElementById("video-source-chip").textContent = name;

    // A new clip means a new chart: different zones, and the old points describe other footage.
    app.chart = { labels: [], total: [], perZone: {} };
    app.zoneDefs.forEach((definition) => {
      app.chart.perZone[definition.name] = [];
    });
    rebuildChart();
    renderGauges(app.latestZones);
    document.getElementById("chart-window").textContent = "waiting for the first samples";

    // Restart the stream so the browser does not keep showing the previous clip's last frame.
    attachVideo();
    clearError();
  } catch (error) {
    showError(`Could not switch to ${name}: ${error.message}`, () => changeSource(name));
    // Put the dropdown back on the clip that is actually playing.
    if (app.source) {
      select.value = app.source;
    }
  } finally {
    app.switching = false;
    select.disabled = false;
    frame.classList.remove("is-loading");
    if (label) {
      label.hidden = true;
    }
  }
}

/**
 * Fetches the zones for one clip and turns them into the gauge list.
 *
 * Why only name and capacity: /api/zones returns polygons too, which the browser does not draw -
 * OpenCV draws them into the stream. Keeping just what the UI uses makes the state small.
 *
 * @param {string|null} source - a clip name, or null for the clip currently playing.
 * @returns {Promise<Array<{name: string, capacity: number}>>} the zone list.
 */
async function loadZones(source = null) {
  const url = source ? `/api/zones?source=${encodeURIComponent(source)}` : "/api/zones";
  const zones = await getJson(url);
  return (Array.isArray(zones) ? zones : []).map((zone) => ({
    name: String(zone.name),
    capacity: Number(zone.capacity) || 0,
  }));
}

/* ---------------------------------------------------------------------------
 * 13. Boot: first load
 * ------------------------------------------------------------------------- */

/**
 * Fills the source dropdown from GET /api/sources.
 *
 * @param {string[]} names - the clip file names the engine accepts.
 * @param {string} current - the clip to select.
 */
function renderSources(names, current) {
  const select = document.getElementById("source-select");
  select.innerHTML = names
    .map((name) =>
      `<option value="${escapeHtml(name)}"${name === current ? " selected" : ""}>` +
      `${escapeHtml(name)}</option>`)
    .join("");
  if (current) {
    select.value = current;
    document.getElementById("video-source-chip").textContent = current;
  }
}

/**
 * Loads the first screen: zones, alert history, chart history, sources, then the stream.
 *
 * Why Promise.allSettled and not Promise.all: one slow or failing endpoint must not stop the
 * others from appearing. A dashboard with gauges, alerts and a video but no chart is far more
 * useful than a blank page, and the error bar still reports the one that failed.
 *
 * @returns {Promise<string[]>} the names of the fetches that failed.
 */
async function loadInitialData() {
  const jobs = {
    zones: getJson("/api/zones"),
    alerts: getJson("/api/alerts?limit=50"),
    history: getJson("/api/history?minutes=10"),
    sources: getJson("/api/sources"),
  };

  const results = await Promise.allSettled(Object.values(jobs));
  const keys = Object.keys(jobs);
  const failures = [];

  const valueOf = (name) => {
    const index = keys.indexOf(name);
    const result = results[index];
    if (result.status === "rejected") {
      failures.push(name);
      return null;
    }
    return result.value;
  };

  const zoneRows = valueOf("zones");
  const alertRows = valueOf("alerts");
  const historyRows = valueOf("history");
  const sourceRows = valueOf("sources");

  if (Array.isArray(zoneRows)) {
    app.zoneDefs = zoneRows.map((zone) => ({
      name: String(zone.name),
      capacity: Number(zone.capacity) || 0,
    }));
  }

  if (Array.isArray(alertRows)) {
    app.alerts = alertRows.map(normaliseAlert);
  }

  const sources = Array.isArray(sourceRows) ? sourceRows : [];
  const current = document.getElementById("source-select").value || sources[0] || "";
  renderSources(sources, app.source || current);

  // The chart needs the zone list to know how many lines to draw, so it is built after zones.
  rebuildChart();
  if (Array.isArray(historyRows)) {
    prefillChart(historyRows);
  }

  renderGauges(app.latestZones);
  renderAlerts(app.alerts);

  // The first snapshot often arrives before these fetches finish, and showSkeletons() would
  // otherwise be the last thing to touch the KPI cards - leaving them blank until the next
  // message. Repainting from the snapshot already in hand closes that gap.
  if (app.lastSnapshot) {
    renderKpis(app.lastSnapshot);
  } else {
    // No message yet: land the skeleton on a real zero rather than leaving a placeholder that
    // never resolves if the socket is slow.
    animateKpi("people", 0);
    animateKpi("peak", 0);
    animateKpi("dwell", 0, "s");
    animateKpi("fps", 0);
  }

  if (failures.length) {
    showError(
      `Could not load: ${failures.join(", ")}. The page will update as soon as the engine answers.`,
      () => retryInitialLoad(),
    );
  }

  return failures;
}

/**
 * Retries the initial load after the user presses Retry.
 *
 * Why not reload the page: a reload would also restart the video stream and lose the chart the
 * operator is watching. Retrying the four fetches is the smaller, faster action.
 */
async function retryInitialLoad() {
  clearError();
  showSkeletons();
  const failures = await loadInitialData();
  if (!failures.length) {
    clearError();
  }
}

/**
 * Replaces the gauges, alert list, KPI numbers and both summaries with shimmering placeholders.
 *
 * Why: the engine takes a second or two to load YOLO, and a blank panel looks broken. A shimmer
 * says "working" without inventing numbers.
 */
function showSkeletons() {
  // Two skeleton gauge cards, built as one string so the markup cannot drift between them.
  const gaugeCard = `
    <div class="gauge-card">
      <div class="skeleton skeleton-ring"></div>
      <div class="skeleton skeleton-line skeleton-gauge-line"></div>
    </div>`;
  document.getElementById("zone-gauges").innerHTML = gaugeCard + gaugeCard;

  // Three rows is about one screenful of a scrolling log: enough to show the shape of it.
  const alertRow = '<li><div class="skeleton skeleton-row"></div></li>';
  document.getElementById("alert-list").innerHTML = alertRow + alertRow + alertRow;

  // A skeleton is a shape, not a number, so it is not announced: aria-busy says "waiting".
  ["people", "peak", "dwell", "fps"].forEach((key) => {
    const node = document.querySelector(`[data-kpi="${key}"]`);
    if (node) {
      node.innerHTML = '<span class="skeleton skeleton-value"></span>';
    }
  });
  document.getElementById("zone-gauges").setAttribute("aria-busy", "true");
  document.getElementById("alert-list").setAttribute("aria-busy", "true");

  document.getElementById("zones-summary").textContent = "…";
  document.getElementById("alerts-summary").textContent = "…";
}

/** Paints the top-bar clock once and then every second. */
function startClock() {
  const node = document.getElementById("clock");
  const tick = () => {
    node.textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

/**
 * Starts the dashboard.
 *
 * Why the sockets and the fetches start together: the first snapshot may arrive before the zone
 * list, and update() tolerates that; waiting for the fetches first would delay the numbers by a
 * round trip for no benefit.
 */
async function boot() {
  startClock();
  setLiveState("waiting");
  bindToggle("toggle-boxes", "boxes");
  bindToggle("toggle-zones", "zones");
  bindToggle("toggle-heat", "heat");
  bindFullscreen();
  bindAlertList();
  bindErrorBar();
  bindSourceSelect();
  showSkeletons();

  connectSocket();

  const failures = await loadInitialData();
  if (!failures.length) {
    clearError();
  }

  // Attach the stream last: the server renders 15 frames a second from the moment the request
  // arrives, so there is no point paying for it before the panels exist.
  attachVideo();
}

/** Wires the dropdown: a change asks the engine to switch clips. */
function bindSourceSelect() {
  const select = document.getElementById("source-select");
  select.addEventListener("change", () => {
    const name = select.value;
    if (name && name !== app.source) {
      changeSource(name);
    }
  });
}

/** Wires the error bar's two buttons. */
function bindErrorBar() {
  document.getElementById("error-close").addEventListener("click", () => clearError());
}

// A stalled MJPEG stream leaves a static frame with no indication that it stopped. Browsers do
// not fire an error event for that, so the state is reported through the pill instead.
window.addEventListener("offline", () => {
  setLiveState("reconnecting");
  showError("This device is offline. The dashboard will reconnect automatically.");
});

window.addEventListener("online", () => {
  clearError();
  // A fresh socket is cheaper than waiting for the backoff timer on a connection that is dead.
  if (app.reconnectTimer) {
    clearTimeout(app.reconnectTimer);
    app.reconnectTimer = null;
  }
  connectSocket();
});

// "loading" fires before images and fonts finish; DOMContentLoaded is enough for our element ids.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
