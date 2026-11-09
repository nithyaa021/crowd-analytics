/* Crowd Analytics dashboard — sample data and render functions.
 *
 * Why sample data lives here and not in index.html: the next step replaces this one object with
 * live WebSocket snapshots. Keeping every number in one place means that swap touches the data
 * source only, never the rendering. Each render function reads a shape rather than a hard-coded
 * value, so the shapes below are a contract:
 *
 *   SAMPLE.zones  -> [{ name, count, capacity, status, avgDwell, maxDwell }]
 *   SAMPLE.alerts -> [{ id, zone, startedAt, peak, capacity, active, keyframe }]
 *   SAMPLE.chart  -> { labels: [...], values: [...], capacity: number }
 *
 * Vanilla JavaScript only. No framework, no build step, no icon library.
 */

"use strict";

/* ---------------------------------------------------------------------------
 * 1. Sample data
 * ------------------------------------------------------------------------- */

/**
 * Picks a reproducible pseudo-random number in [0, 1).
 *
 * Why not Math.random(): the chart must look identical on every reload, so a screenshot in the
 * docs always matches what a reviewer sees. A seeded generator gives that for free.
 *
 * @param {number} seed - any integer; the same seed always yields the same sequence.
 * @returns {number} a value between 0 and 1.
 */
function seeded(seed) {
  // A sine-based hash: cheap, deterministic, and good enough for cosmetic wobble.
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Builds the 60 headcount samples shown in the line chart.
 *
 * Why 60: sixty points across a 2-minute window is dense enough to look like real telemetry and
 * light enough to stay readable on a phone.
 *
 * @returns {{labels: string[], values: number[]}} labels as mm:ss, values as people in frame.
 */
function buildHeadcountSeries() {
  const labels = [];
  const values = [];
  const now = new Date();

  for (let i = 0; i < 60; i += 1) {
    // Walk backwards from "now", one sample every 2 seconds.
    const moment = new Date(now.getTime() - (59 - i) * 2000);
    const minutes = String(moment.getMinutes()).padStart(2, "0");
    const seconds = String(moment.getSeconds()).padStart(2, "0");
    labels.push(`${minutes}:${seconds}`);

    // A slow rise into the middle of the window, then a partial recovery: the shape of a
    // crowd building at an entrance and thinning out once the queue moves.
    const trend = 6 + 5 * Math.sin((i / 59) * Math.PI);
    const noise = (seeded(i) - 0.5) * 3;
    values.push(Math.max(0, Math.round(trend + noise)));
  }

  return { labels, values };
}

const SAMPLE = {
  source: "crowded.mp4",
  sources: ["crowded.mp4", "mid.mp4", "normal.mp4"],
  fps: 8.4,
  peakPeople: 15,

  // Two zones on purpose: one comfortably OK and one over capacity, so both visual states of
  // the gauge and the status chip are visible on a single screen.
  // overFor is the seconds count from AlertDebouncer.over_for; the banner reads only this.
  zones: [
    {
      name: "Main Zone",
      count: 12,
      capacity: 10,
      status: "OVER",
      overFor: 12,
      avgDwell: 18.4,
      maxDwell: 47.0,
    },
    {
      name: "Entrance",
      count: 4,
      capacity: 8,
      status: "OK",
      overFor: 0,
      avgDwell: 6.2,
      maxDwell: 11.5,
    },
  ],

  // Six alerts: the newest still running, the rest closed. Two severities so the coloured
  // left bar and both tag styles are exercised.
  alerts: [
    {
      id: 6,
      zone: "Main Zone",
      startedAt: "14:32:08",
      peak: 12,
      capacity: 10,
      active: true,
      keyframe: null,
    },
    {
      id: 5,
      zone: "Main Zone",
      startedAt: "14:24:51",
      peak: 13,
      capacity: 10,
      active: false,
      keyframe: null,
    },
    {
      id: 4,
      zone: "Main Zone",
      startedAt: "14:16:02",
      peak: 11,
      capacity: 10,
      active: false,
      keyframe: null,
    },
    {
      id: 3,
      zone: "Entrance",
      startedAt: "14:07:44",
      peak: 9,
      capacity: 8,
      active: false,
      keyframe: null,
    },
    {
      id: 2,
      zone: "Main Zone",
      startedAt: "13:58:20",
      peak: 14,
      capacity: 10,
      active: false,
      keyframe: null,
    },
    {
      id: 1,
      zone: "Entrance",
      startedAt: "13:49:05",
      peak: 8,
      capacity: 8,
      active: false,
      keyframe: null,
    },
  ],

  chart: buildHeadcountSeries(),
  // A flat capacity reference line at 10, so "above the line" means "over capacity".
  chartCapacity: 10,
};

/* ---------------------------------------------------------------------------
 * 2. Small helpers
 * ------------------------------------------------------------------------- */

/** Radius of the gauge ring in SVG units; the stroke math below depends on it. */
const GAUGE_RADIUS = 52;
/** Circumference of that ring: 2 * PI * 52 ≈ 326.73 SVG units. */
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS;

/**
 * Escapes text before it goes into an HTML template.
 *
 * Why: zone names come from zones.json, which a person edits by hand. A name containing "<" would
 * otherwise break the markup, and in the next step this text arrives over the network.
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
 * @param {string} status - "OK", "NEAR" or "OVER".
 * @returns {string} "ok", "near" or "over".
 */
function statusClass(status) {
  return String(status || "OK").toLowerCase();
}

/**
 * Returns a status-appropriate inline SVG icon.
 *
 * Why inline SVG: the brief forbids an icon library, and a 3-line path is smaller than the
 * request that would fetch an icon font.
 *
 * @param {string} status - "OK", "NEAR" or "OVER".
 * @returns {string} an inline <svg> string safe to insert into HTML.
 */
function statusIcon(status) {
  if (status === "OVER") {
    // A filled circle with an exclamation: "stop, something is wrong".
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"
      stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle>
      <path d="M12 7v6"></path><path d="M12 17h.01"></path></svg>`;
  }
  if (status === "NEAR") {
    // A triangle warning: "watch this".
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 3 2 20h20L12 3z"></path><path d="M12 9v4"></path></svg>`;
  }
  // A tick: "fine".
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5"></path></svg>`;
}

/**
 * Formats seconds as a compact dwell string.
 *
 * Example: 18.4 -> "18.4 s"; 47.0 -> "47 s".
 *
 * @param {number} seconds - dwell time in seconds.
 * @returns {string} the formatted value with its unit.
 */
function formatDwell(seconds) {
  const value = Number(seconds) || 0;
  return value >= 10 ? `${Math.round(value)} s` : `${value.toFixed(1)} s`;
}

/* ---------------------------------------------------------------------------
 * 3. Renderers
 * ------------------------------------------------------------------------- */

/**
 * Writes the four KPI cards.
 *
 * Why this is its own function: the KPI row is the first thing anyone reads, and it is the most
 * likely place for a "500" or "NaN" to appear if a field is missing. One function means one place
 * to fix it.
 *
 * @param {object} data - a snapshot-shaped object (see the SAMPLE shape above).
 */
function renderKpis(data) {
  const totalPeople = data.zones.reduce((sum, zone) => sum + zone.count, 0);
  const dwellValues = data.zones.map((zone) => zone.avgDwell);
  // The headline dwell is the busiest zone's, not the mean of the means: a quiet zone would
  // otherwise drag the number down and hide a real bottleneck.
  const busiest = data.zones.reduce(
    (worst, zone) => (zone.avgDwell > worst.avgDwell ? zone : worst),
    { avgDwell: 0, name: "—" },
  );

  setKpi("people", String(totalPeople), `${data.zones.length} zones monitored`);
  setKpi("peak", String(data.peakPeople), "highest frame this session");
  setKpi("dwell", formatDwell(busiest.avgDwell), `longest in ${busiest.name}`);
  setKpi("fps", data.fps.toFixed(1), "detections per second");

  // The header chip mirrors the KPI so the two can never disagree.
  document.getElementById("fps-chip").textContent = data.fps.toFixed(1);
}

/**
 * Writes one KPI card's number and caption.
 *
 * @param {string} key - "people", "peak", "dwell" or "fps".
 * @param {string} value - already-formatted number text.
 * @param {string} caption - the small grey line under the label.
 */
function setKpi(key, value, caption) {
  const valueNode = document.querySelector(`[data-kpi="${key}"]`);
  const captionNode = document.querySelector(`[data-kpi-caption="${key}"]`);
  if (valueNode) {
    // For dwell and fps the unit is rendered smaller, so it is appended as its own span.
    if (key === "dwell") {
      const parts = value.split(" ");
      valueNode.innerHTML =
        `${escapeHtml(parts[0])}<span class="unit">${escapeHtml(parts[1] || "")}</span>`;
    } else {
      valueNode.textContent = value;
    }
  }
  if (captionNode) {
    captionNode.textContent = caption;
  }
}

/**
 * Draws one SVG ring gauge per zone.
 *
 * Why SVG and not a canvas or a progress bar: a ring shows "how full" and "how much room is left"
 * at the same time, reads well at 90 px, and needs no library. The fill is one circle whose
 * stroke-dashoffset is shortened; see docs/explained/ui.md for the arithmetic.
 *
 * @param {object[]} zones - [{ name, count, capacity, status, avgDwell }]
 */
function renderGauges(zones) {
  const container = document.getElementById("zone-gauges");

  container.innerHTML = zones
    .map((zone) => {
      // Clip at 1: an over-capacity zone cannot fill more than a full ring, and the OVER chip
      // already says the rest. Without the clip the dashoffset would go negative and the arc
      // would wrap around from the start again, which looks like an empty ring.
      const fraction = zone.capacity > 0 ? Math.min(zone.count / zone.capacity, 1) : 0;
      // dashoffset = the part of the circumference that stays hidden.
      const offset = GAUGE_CIRCUMFERENCE * (1 - fraction);
      const status = zone.status || "OK";
      const isHot = status === "OVER" ? " is-hot" : "";

      return `
        <div class="gauge-card${isHot}">
          <svg class="gauge" viewBox="0 0 120 120" role="img"
               aria-label="${escapeHtml(zone.name)}: ${zone.count} of ${zone.capacity} people, ${status}">
            <!-- Rotate -90 deg so the ring starts at 12 o'clock instead of 3 o'clock. -->
            <g transform="rotate(-90 60 60)">
              <circle class="gauge-track" cx="60" cy="60" r="${GAUGE_RADIUS}"
                      fill="none" stroke-width="9"></circle>
              <circle class="gauge-arc" cx="60" cy="60" r="${GAUGE_RADIUS}"
                      fill="none" stroke-width="9"
                      stroke="${status === "OVER" ? "var(--crit)" : status === "NEAR" ? "var(--warn)" : "var(--ok)"}"
                      stroke-dasharray="${GAUGE_CIRCUMFERENCE.toFixed(2)}"
                      stroke-dashoffset="${offset.toFixed(2)}"></circle>
            </g>
            <text class="gauge-num" x="60" y="58" text-anchor="middle">${zone.count}</text>
            <text class="gauge-cap" x="60" y="76" text-anchor="middle">/ ${zone.capacity}</text>
          </svg>
          <div class="gauge-name" title="${escapeHtml(zone.name)}">${escapeHtml(zone.name)}</div>
          <span class="status-chip ${statusClass(status)}">
            ${statusIcon(status)}${escapeHtml(status)}
          </span>
          <div class="gauge-dwell">avg ${formatDwell(zone.avgDwell)}</div>
        </div>`;
    })
    .join("");

  // Summary chip: how many zones are over, which is the single number worth reading at a glance.
  const overCount = zones.filter((zone) => zone.status === "OVER").length;
  const summary = document.getElementById("zones-summary");
  summary.textContent = overCount > 0 ? `${overCount}/${zones.length} over` : "all normal";
  summary.style.color = overCount > 0 ? "var(--crit)" : "var(--ok)";
}

/**
 * Draws the alert log, or the empty state when there is nothing to show.
 *
 * Why the empty state matters: an empty list looks identical to a broken panel. "No alerts. All
 * zones normal." tells the operator the difference in three words.
 *
 * @param {object[]} alerts - newest first, as produced by the backend.
 */
function renderAlerts(alerts) {
  const list = document.getElementById("alert-list");
  const summary = document.getElementById("alerts-summary");

  if (!alerts.length) {
    list.innerHTML = `
      <li class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M20 6 9 17l-5-5"></path>
        </svg>
        <span>No alerts. All zones normal.</span>
      </li>`;
    summary.textContent = "0";
    summary.style.color = "var(--ok)";
    return;
  }

  list.innerHTML = alerts
    .map((alert) => {
      // Severity is derived, not stored: a peak far above capacity is critical, a marginal
      // overshoot is a warning. Deriving it keeps one source of truth for the colour.
      const ratio = alert.capacity > 0 ? alert.peak / alert.capacity : 0;
      const severity = alert.active ? "crit" : ratio >= 1.3 ? "crit" : "warn";
      const tagClass = alert.active ? "active" : "cleared";
      const tagText = alert.active ? "Active" : "Cleared";

      // A real thumbnail when the backend supplies a keyframe, a placeholder frame otherwise.
      const thumb = alert.keyframe
        ? `<img src="${escapeHtml(alert.keyframe)}" alt="Evidence for ${escapeHtml(alert.zone)}">`
        : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
             <rect x="3" y="4" width="18" height="16" rx="2"></rect>
             <circle cx="9" cy="10" r="1.6"></circle>
             <path d="m4 18 5-5 4 4 3-3 4 4"></path>
           </svg>`;

      return `
        <li class="alert-row${alert.active ? " is-active" : ""}">
          <span class="alert-sev ${severity}" aria-hidden="true"></span>
          <span class="alert-thumb">${thumb}</span>
          <span class="alert-main">
            <span class="alert-top">
              <span class="alert-time">${escapeHtml(alert.startedAt)}</span>
              <span class="alert-zone">${escapeHtml(alert.zone)}</span>
            </span>
            <span class="alert-meta">peak ${alert.peak}/${alert.capacity}</span>
          </span>
          <span class="alert-tag ${tagClass}">${tagText}</span>
        </li>`;
    })
    .join("");

  const activeCount = alerts.filter((alert) => alert.active).length;
  summary.textContent = `${activeCount} active / ${alerts.length}`;
  summary.style.color = activeCount > 0 ? "var(--crit)" : "var(--muted)";
}

/** Holds the Chart.js instance so a re-render updates it instead of stacking a second canvas. */
let headcountChart = null;

/**
 * Draws the headcount line with a flat capacity reference line.
 *
 * Why update instead of recreate: Chart.js keeps a canvas context. Calling new Chart() repeatedly
 * on the same canvas leaks instances and eventually freezes the tab during a long demo.
 *
 * @param {{labels: string[], values: number[]}} series - the samples to plot.
 * @param {number} capacity - the flat capacity line.
 */
function renderChart(series, capacity) {
  const canvas = document.getElementById("headcount-chart");
  const context = canvas.getContext("2d");

  // A vertical gradient makes the fill read as "volume" rather than a flat block of colour.
  const gradient = context.createLinearGradient(0, 0, 0, 190);
  gradient.addColorStop(0, "rgba(56, 189, 248, 0.34)");
  gradient.addColorStop(1, "rgba(56, 189, 248, 0.02)");

  const capacityLine = series.values.map(() => capacity);

  const config = {
    type: "line",
    data: {
      labels: series.labels,
      datasets: [
        {
          label: "People",
          data: series.values,
          borderColor: "#38bdf8",
          backgroundColor: gradient,
          borderWidth: 2,
          fill: true,
          tension: 0.35,
          // No dots: 60 of them would look like a scatter plot, not a trend.
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: "#38bdf8",
        },
        {
          label: "Capacity",
          data: capacityLine,
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
            // Show every 12th label so 60 timestamps do not overlap into a grey smear.
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

  if (headcountChart) {
    headcountChart.data = config.data;
    headcountChart.update("none");
    return;
  }
  headcountChart = new Chart(context, config);
}

/* ---------------------------------------------------------------------------
 * 4. Banner, clock, overlays
 * ------------------------------------------------------------------------- */

/**
 * Shows or hides the congestion banner, and fills in its text.
 *
 * Why the text is assembled here rather than in the HTML: the same banner serves any zone, and
 * the count and duration change every second in the live version.
 *
 * @param {{name: string, count: number, capacity: number, overFor: number}|null} problem
 *   the worst congested zone, or null to hide the banner. The field is called "name" because
 *   that is what the engine snapshot sends for a zone; keeping the same key now means the live
 *   data can drive this function unchanged in the next step.
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
    `<span class="banner-count">for ${Math.round(problem.overFor || 0)} s</span>`;
  banner.hidden = false;
}

/**
 * Finds the zone that has been over capacity the longest, for the banner.
 *
 * @param {object[]} zones - zones with an optional overFor (seconds).
 * @returns {object|null} the worst zone, or null when nothing is over.
 */
function worstZone(zones) {
  const over = zones.filter((zone) => zone.status === "OVER");
  if (!over.length) {
    return null;
  }
  return over.reduce((worst, zone) =>
    (zone.overFor || 0) > (worst.overFor || 0) ? zone : worst,
  );
}

/**
 * Paints the top-bar clock once and then every second.
 *
 * Why local time and not video time: this is the operator's clock. Video time is a different
 * number and already appears in the KPI row and the alert log.
 */
function startClock() {
  const node = document.getElementById("clock");
  const tick = () => {
    node.textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

/** Current overlay state; in the next step this becomes the /video query string. */
const overlays = { boxes: true, zones: true, heat: false };

/**
 * Wires one overlay toggle button to the shared state.
 *
 * Why aria-pressed is the only stored truth: the CSS colours the chip from that attribute, so the
 * visual state and what a screen reader announces can never drift apart.
 *
 * @param {string} id - the button's element id.
 * @param {string} key - the key in the overlays object.
 */
function bindToggle(id, key) {
  const button = document.getElementById(id);
  button.addEventListener("click", () => {
    overlays[key] = !overlays[key];
    button.setAttribute("aria-pressed", String(overlays[key]));
  });
  button.setAttribute("aria-pressed", String(overlays[key]));
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
 * 5. States: skeletons and boot
 * ------------------------------------------------------------------------- */

/**
 * Replaces the gauges and alert list with shimmering placeholders.
 *
 * Why bother: the real app takes a second or two to load the model, and a blank panel looks
 * broken. A shimmer says "working" without inventing numbers.
 */
function showSkeletons() {
  const gauges = document.getElementById("zone-gauges");
  gauges.innerHTML = `
    <div class="gauge-card"><div class="skeleton skeleton-ring"></div>
      <div class="skeleton skeleton-line" style="width:70%;margin:8px auto 0"></div></div>
    <div class="gauge-card"><div class="skeleton skeleton-ring"></div>
      <div class="skeleton skeleton-line" style="width:70%;margin:8px auto 0"></div></div>`;

  const list = document.getElementById("alert-list");
  list.innerHTML = `
    <li><div class="skeleton skeleton-row"></div></li>
    <li><div class="skeleton skeleton-row"></div></li>
    <li><div class="skeleton skeleton-row"></div></li>`;

  // The KPI numbers become skeleton bars, so no stale figure is visible while loading.
  ["people", "peak", "dwell", "fps"].forEach((key) => {
    const node = document.querySelector(`[data-kpi="${key}"]`);
    if (node) {
      node.innerHTML = '<span class="skeleton skeleton-value" style="display:block"></span>';
    }
  });

  document.getElementById("zones-summary").textContent = "…";
  document.getElementById("alerts-summary").textContent = "…";
}

/** Fills the source dropdown from the sample list. */
function renderSources(names, current) {
  const select = document.getElementById("source-select");
  select.innerHTML = names
    .map(
      (name) =>
        `<option value="${escapeHtml(name)}"${name === current ? " selected" : ""}>` +
        `${escapeHtml(name)}</option>`,
    )
    .join("");
  document.getElementById("video-source-chip").textContent = current;
}

/**
 * Renders the whole dashboard from one data object.
 *
 * Why a single entry point: the next step calls exactly this with a WebSocket snapshot instead of
 * SAMPLE, and every panel updates together. If each panel rendered itself from its own source,
 * the screen could show two different moments at once.
 *
 * @param {object} data - a SAMPLE-shaped object.
 */
function renderAll(data) {
  renderKpis(data);
  renderGauges(data.zones);
  renderAlerts(data.alerts);
  renderChart(data.chart, data.chartCapacity);
  // The banner names whichever zone has been over capacity the longest; the sample carries
  // overFor on each zone, and the live snapshot will supply the same field.
  renderBanner(worstZone(data.zones));
}

/** Wires the temporary preview buttons that prove each visual state. */
function bindDevControls() {
  document.getElementById("dev-banner-ok").addEventListener("click", () => {
    renderBanner(null);
  });
  document.getElementById("dev-banner-over").addEventListener("click", () => {
    renderBanner(SAMPLE.zones[0]);
  });
  document.getElementById("dev-skeleton").addEventListener("click", () => {
    showSkeletons();
    // A short delay so the shimmer is actually visible before the data returns.
    setTimeout(() => renderAll(SAMPLE), 1600);
  });
  document.getElementById("dev-empty").addEventListener("click", () => {
    renderAlerts([]);
    // Restore the real log after a moment, so the button is a preview and not a one-way switch.
    setTimeout(() => renderAlerts(SAMPLE.alerts), 2200);
  });
}

/**
 * Starts the dashboard: skeleton first, then the sample data.
 *
 * Why a short delay before rendering: it makes the loading state visible on a fast local machine,
 * so the shimmer can be reviewed at all. In the next step this is replaced by "wait for the first
 * WebSocket snapshot".
 */
function boot() {
  startClock();
  renderSources(SAMPLE.sources, SAMPLE.source);
  bindToggle("toggle-boxes", "boxes");
  bindToggle("toggle-zones", "zones");
  bindToggle("toggle-heat", "heat");
  bindFullscreen();
  bindDevControls();

  showSkeletons();
  setTimeout(() => renderAll(SAMPLE), 700);
}

// "loading" fires before images and fonts finish; DOMContentLoaded is enough for our element ids.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
