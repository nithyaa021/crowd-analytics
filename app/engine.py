"""Runs the video loop in a background thread and keeps the newest result in memory.

Why this file exists: the web server must answer requests instantly, but reading a video and
running YOLO takes about 140 ms per frame. So the slow work lives in one background thread
(Engine) and every web request just reads the newest finished result (SharedState). No request
ever waits for the model.

The two halves only meet at SharedState, protected by one lock. The rule everywhere: share copies
or immutable values, never a live object that another thread is mutating. A frame handed out of
SharedState is a copy, so the engine may overwrite its own buffer freely.
"""

import copy
import threading
import time

import cv2
import numpy as np

from app import config, db
from app.analytics import AlertDebouncer, DwellTracker, HeatmapAccumulator, SpeedTracker
from app.vision import Detector, resize_frame
from app.zones import Zone, count_by_zone, draw_zones, load_zones, status_for

# Frame rate to assume when a clip reports broken metadata, so timings never divide by zero.
DEFAULT_FPS = 25.0

# Colour of a person's box and of the dot on their feet, in OpenCV's BGR order.
BOX_COLOR = (0, 255, 0)
FOOT_COLOR = (0, 0, 255)

# Box thickness and foot-dot radius, in pixels.
BOX_THICKNESS = 2
DOT_RADIUS = 4

# Reserved zone name used for the whole-frame total in the headcount table.
TOTAL_ZONE = "ALL"


def empty_snapshot(source: str) -> dict:
    """Returns a valid, all-zero snapshot for the moment before the engine's first frame.

    Why this exists: a browser connects to /ws immediately, while YOLO is still loading. Sending
    `{}` would break the contract and force every client to guard against missing keys. Sending a
    well-formed "nothing yet" snapshot means the dashboard can render its first frame without a
    single special case.

    Example: empty_snapshot("crowded.mp4") gives ts 0, fps 0, total_people 0, zones [].
    """
    return {
        "ts": 0.0,
        "source": source,
        "fps": 0.0,
        "total_people": 0,
        "peak_people": 0,
        "zones": [],
        "alerts_active": 0,
        "new_alert": None,
    }


class SharedState:
    """Holds the newest frame and the newest snapshot so two threads can hand work over safely.

    Why one lock for everything: the dashboard's video and its numbers must describe the same
    moment. With separate locks a reader could get a frame from 10.0 s and a snapshot from
    10.5 s, and the boxes on screen would not match the counts beside them.

    Why copies on the way out: the engine keeps writing into its own frame buffer. A reader
    holding a reference would see the picture change underneath it - or change halfway through
    the JPEG encoder, which produces a torn image.
    """

    def __init__(self, initial_snapshot: dict | None = None) -> None:
        """Starts empty, but with a well-formed snapshot so the contract holds from second zero.

        Example: SharedState() then get() returns (None, [], {"ts": 0.0, "zones": [], ...}).
        """
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._people: list = []
        # The heat "layer" is the pair overlay() needs, computed once per frame by the engine and
        # reused by every /video request, so no request has to re-blur the whole heatmap.
        self._heat_colour: np.ndarray | None = None
        self._heat_mask: np.ndarray | None = None
        self._snapshot: dict = initial_snapshot or empty_snapshot(config.DEFAULT_SOURCE)

    def set(self, frame: np.ndarray | None = None, people: list | None = None,
            heat: tuple[np.ndarray, np.ndarray] | None = None,
            snapshot: dict | None = None) -> None:
        """Replaces whichever pieces are supplied, leaving the rest untouched, under one lock.

        Why optional arguments: the engine updates the snapshot every frame but the heat only
        when it has one, so callers pass just what changed and the call stays short.

        Example: set(snapshot=snap) updates the numbers without copying a frame again.
        """
        with self._lock:
            if frame is not None:
                # copy() so the engine can safely overwrite its own buffer on the next frame.
                self._frame = frame.copy()
            if people is not None:
                # People are tiny dataclasses, but a list copy still stops the caller appending
                # to the list we are reading.
                self._people = list(people)
            if heat is not None:
                colour, mask = heat
                self._heat_colour = colour
                self._heat_mask = mask
            if snapshot is not None:
                # deepcopy because the snapshot nests dicts and lists a reader may walk through.
                self._snapshot = copy.deepcopy(snapshot)

    def get(self) -> tuple[np.ndarray | None, list, dict]:
        """Returns (frame copy, people, snapshot) read together under one lock.

        Why one call instead of three getters: three separate calls could interleave with an
        engine update and return a frame from one moment and a snapshot from another. Reading
        them in a single locked block guarantees they belong to the same frame.

        Example: a frame at video 10.0 s always comes back with ts 10.0, never 10.5.
        """
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            return frame, list(self._people), copy.deepcopy(self._snapshot)

    def get_heat(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Returns the heat layer the engine last computed, or None if there is none yet.

        Why separate from get(): a request that asks for boxes only never needs to copy two
        full-size heat arrays, and /video is the hot path.
        """
        with self._lock:
            if self._heat_colour is None or self._heat_mask is None:
                return None
            return self._heat_colour, self._heat_mask


def list_clips() -> list[str]:
    """Returns the file names of every demo clip, sorted, as a plain allow-list.

    Why an allow-list and not a path check: set_source must never accept a path from the
    browser. Building the list from the actual folder contents means the only values that can
    ever be accepted are names this function already returned.

    Example: ["crowded.mp4", "mid.mp4", "normal.mp4"].
    """
    return sorted(path.name for path in config.VIDEO_DIR.glob("*.mp4"))


def source_fps(capture: cv2.VideoCapture) -> float:
    """Reads a clip's frame rate, falling back to 25 when the metadata is unusable.

    Why: every time in the snapshot is frame_index / fps. A NaN or zero frame rate would make
    all of them nonsense, so a sane fallback beats crashing on a bad download.

    Example: a broken file reporting nan gives 25.0, so frame 50 is reported as 2.0 s.
    """
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps <= 0:
        return DEFAULT_FPS
    return float(fps)


class Engine(threading.Thread):
    """The one background thread that reads video, runs the model and publishes a snapshot.

    Why a Thread subclass: it starts with engine.start(), and being a daemon means a closed
    terminal never leaves a hidden process holding a video file open.
    """

    def __init__(self, state: SharedState | None = None) -> None:
        """Sets up the thread but does not start it, so the caller controls the lifetime.

        Why the detector is built here and not per clip: loading YOLO weights takes a second or
        two, and reloading them on every replay would freeze the dashboard between loops.
        """
        super().__init__(daemon=True, name="CrowdEngine")
        self.state = state or SharedState()
        # Start the snapshot with the configured clip's name, so the UI shows the right source
        # even during the couple of seconds before the first frame is analysed.
        self.state.set(snapshot=empty_snapshot(config.DEFAULT_SOURCE))
        self.detector = Detector()
        # Guarded because the API thread changes the source while this thread is mid-clip.
        self._source_lock = threading.Lock()
        self._source = config.DEFAULT_SOURCE
        # A flag rather than a direct call: the API sets it, and the loop acts on it between
        # frames, never in the middle of one.
        self._restart_requested = False
        # Processing durations of recent frames, for the moving-average FPS.
        self._frame_times: list[float] = []
        # Cache of parsed zones per clip name. Why: /video renders up to 15 frames a second and
        # re-reading zones.json for every one of them is 15 file reads a second for data that
        # only changes when the operator runs auto_zones.py.
        self._zones_cache: dict[str, list[Zone]] = {}
        # Set by run() once a clip has published its first frame, so the smoke test can wait
        # for "the engine is actually producing" instead of guessing with a sleep.
        self.ready = threading.Event()

    # ---------- called from the API thread ----------

    def set_source(self, name: str) -> None:
        """Asks the loop to switch clips, but only if the name is on the allow-list.

        Why only set a flag: this runs in a web request thread. Closing the capture or resetting
        the detector from here would yank the file handle out from under the video loop. The
        loop notices the flag at the top of its next frame and rebuilds itself there.

        Example: set_source("mid.mp4") is accepted; set_source("../zones.json") raises.
        """
        if name not in list_clips():
            raise ValueError(f"Unknown source: {name}")
        with self._source_lock:
            self._source = name
            self._restart_requested = True

    def current_source(self) -> str:
        """Returns the clip the loop is playing, so the snapshot can report it.

        Why a lock for one string: the GIL makes a bare read safe in practice, but being
        explicit costs nothing and documents that two threads touch this value.
        """
        with self._source_lock:
            return self._source

    # ---------- the loop ----------

    def run(self) -> None:
        """Loops forever: play the clip, then replay it from the start with everything reset.

        Why forever: this is a live dashboard. When the footage ends, replaying it is more
        honest than freezing on the last frame with a crowd that never moves again.

        Why the try/except: a crashed thread would leave a permanently frozen dashboard with no
        explanation. Printing and continuing keeps the app alive and says what happened.
        """
        while True:
            try:
                self._play_clip(self.current_source())
            except Exception as error:  # noqa: BLE001 - a dead thread is worse than a logged error
                print(f"[engine] stopped on {self.current_source()}: {error!r}")
                time.sleep(1.0)
            with self._source_lock:
                self._restart_requested = False

    def _play_clip(self, source_name: str) -> None:
        """Plays one clip start to finish, then returns so run() can replay it.

        Everything that remembers (detector tracks, dwell, heat, debouncers) is rebuilt here, so
        a replay starts from a clean slate instead of inheriting the previous loop's state.
        """
        clip_path = config.VIDEO_DIR / source_name
        capture = cv2.VideoCapture(str(clip_path))
        if not capture.isOpened():
            raise RuntimeError(f"Cannot open clip: {clip_path}")

        fps = source_fps(capture)
        # Zones belong to this camera view, so they are loaded per clip, not globally.
        zones = load_zones(config.ZONES_FILE, source_name)

        self.detector.reset()
        dwell = DwellTracker()
        speeds = SpeedTracker()
        debouncers = {zone.name: AlertDebouncer(zone.name) for zone in zones}
        active_alerts: dict[str, int] = {}   # zone name -> the alert id currently open
        # Busiest count seen since each zone's alert opened, so update_peak writes only on a rise.
        peak_counts: dict[str, int] = {}
        heatmap: HeatmapAccumulator | None = None
        peak_people = 0
        next_headcount_at = 0.0
        frame_index = 0

        try:
            while not self._restart_requested:
                # grab() advances cheaply; only every STRIDE-th frame is decoded and analysed.
                if not capture.grab():
                    break
                if frame_index % config.STRIDE == 0:
                    ok, frame = capture.retrieve()
                    if not ok:
                        break
                    frame = resize_frame(frame, config.FRAME_WIDTH)
                    if heatmap is None:
                        # The heatmap must match the real frame size, known only from frame one.
                        heatmap = HeatmapAccumulator(frame.shape[1], frame.shape[0])

                    started = time.perf_counter()
                    now = frame_index / fps
                    people = self.detector.track(frame)
                    peak_people = max(peak_people, len(people))

                    grouped = count_by_zone(zones, people)
                    counts = {name: len(group) for name, group in grouped.items()}
                    members = {name: [person.track_id for person in group]
                               for name, group in grouped.items()}

                    dwell.update(now, members)
                    # Movement velocity for this moment, keyed by track ID. See chapter 4.4.
                    speed_map = speeds.update(now, people)
                    # One point per person: the same foot pixel the zone test uses.
                    heatmap.add([person.foot for person in people])

                    new_alert = self._update_alerts(zones, counts, debouncers, active_alerts,
                                                    peak_counts, now, people, source_name)
                    if now >= next_headcount_at:
                        self._save_headcounts(counts)
                        next_headcount_at = now + config.HEADCOUNT_INTERVAL

                    snapshot = self._build_snapshot(zones, counts, dwell, speed_map, grouped,
                                                    now, peak_people, debouncers, active_alerts,
                                                    source_name, new_alert)
                    self.state.set(frame=frame, people=people, heat=heatmap.layer(),
                                   snapshot=snapshot)
                    self._record_frame_time(time.perf_counter() - started)
                    self.ready.set()
                frame_index += 1
        finally:
            # Releasing in `finally` frees the file handle even if a frame raised, which on
            # Windows is what stops the clip staying locked for the next replay.
            capture.release()
            self._close_alerts(active_alerts, peak_counts)

    def _update_alerts(self, zones: list[Zone], counts: dict[str, int],
                       debouncers: dict[str, AlertDebouncer], active_alerts: dict[str, int],
                       peak_counts: dict[str, int], now: float, people: list,
                       source_name: str) -> dict | None:
        """Feeds each zone's count into its debouncer and acts on TRIGGERED / CLEARED.

        Why it returns new_alert: the snapshot must carry the alert for exactly one publication,
        so the alert information travels from here to the snapshot builder instead of being stored
        somewhere and cleared later.

        Why peak_counts is tracked in memory first: a database write on every frame while an alert
        is open would mean eight connections a second for a value that almost never changes. It is
        written only when the peak actually rises.

        Example: 7 people in a capacity-4 zone at 31.5 s returns
        {"id": 1, "zone": "Main Zone", "keyframe": "/evidence/alert_1.jpg"}.
        """
        new_alert: dict | None = None
        for zone in zones:
            count = counts[zone.name]
            event = debouncers[zone.name].update(now, count, zone.capacity)
            if event == "TRIGGERED":
                new_alert = self._open_alert(zone, count, now, people, zones, counts,
                                             source_name, active_alerts)
                peak_counts[zone.name] = count
            elif event == "CLEARED":
                self._finish_alert(zone.name, active_alerts, peak_counts)

            # While an alert is open, its stored peak must follow the busiest moment.
            alert_id = active_alerts.get(zone.name)
            if alert_id is not None and count > peak_counts.get(zone.name, 0):
                peak_counts[zone.name] = count
                db.update_peak(alert_id, count)
        return new_alert

    def _open_alert(self, zone: Zone, count: int, now: float, people: list, zones: list[Zone],
                    counts: dict[str, int], source_name: str,
                    active_alerts: dict[str, int]) -> dict:
        """Inserts the alert row, saves the evidence photo, and returns the new_alert payload.

        Why insert before saving the photo: the file name is alert_<id>.jpg, so the id must exist
        first. If the photo then fails, the alert still exists with a null keyframe - a missing
        picture is much better than a missing alert.
        """
        alert_id = db.insert_alert(zone.name, source_name, now, count, zone.capacity, None)
        keyframe = self._save_evidence(alert_id, people, zones, counts, now)
        if keyframe is not None:
            db.set_keyframe(alert_id, keyframe)
        active_alerts[zone.name] = alert_id
        print(f"[engine] {now:6.1f}s  {zone.name} {count}/{zone.capacity} TRIGGERED "
              f"(alert {alert_id}, keyframe {keyframe})")
        return {"id": int(alert_id), "zone": zone.name, "keyframe": keyframe}

    def _finish_alert(self, zone_name: str, active_alerts: dict[str, int],
                      peak_counts: dict[str, int] | None = None) -> None:
        """Closes the open alert for one zone, if there is one.

        Why the guard: CLEARED can only arrive while active, but a defensive check keeps a future
        bug from raising inside the video loop and killing the engine.

        Why peak_counts is cleared too: the in-memory peak belongs to the alert that just ended.
        Leaving it behind would make the *next* alert in that zone ignore any low starting count.
        """
        alert_id = active_alerts.pop(zone_name, None)
        if peak_counts is not None:
            peak_counts.pop(zone_name, None)
        if alert_id is None:
            return
        db.end_alert(alert_id)
        print(f"[engine] alert {alert_id} for {zone_name} CLEARED")

    def _close_alerts(self, active_alerts: dict[str, int],
                      peak_counts: dict[str, int] | None = None) -> None:
        """Ends every alert still open when a clip stops, so none looks live forever.

        Why: when the clip ends or the operator switches source, the crowd is no longer being
        watched. Leaving rows open would show an alert for a video that is not even playing.
        """
        for zone_name in list(active_alerts):
            self._finish_alert(zone_name, active_alerts, peak_counts)

    def _save_headcounts(self, counts: dict[str, int]) -> None:
        """Writes one row per zone plus a total row for the whole frame, every 2 video seconds.

        Why a total row as well: the dashboard charts "people in the picture" and "people in this
        zone" on different scales, and the total cannot be summed from per-zone rows without a
        query per refresh. It is stored under the reserved name "ALL".

        Example: {"Main Zone": 7} writes ("...T14:03", "Main Zone", 7) and ("...T14:03", "ALL", 7).
        """
        timestamp = db.utc_now_iso()
        for zone_name, count in counts.items():
            db.add_headcount(timestamp, zone_name, count)
        db.add_headcount(timestamp, TOTAL_ZONE, sum(counts.values()))

    def _save_evidence(self, alert_id: int, people: list, zones: list[Zone],
                       counts: dict[str, int], now: float) -> str | None:
        """Writes the current annotated frame to evidence/alert_<id>.jpg and returns its URL.

        Why a photo at all: an alert row is only numbers. A picture of the moment is what lets a
        human check afterwards whether the alert was real.

        Why the URL and not the disk path: the row is read by the browser, and the browser can
        only fetch things served under /evidence.

        Returns None if the frame is missing or the write failed, so the alert row survives.
        """
        frame, _, _ = self.state.get()
        if frame is None:
            return None

        # Draw on a copy, so the frame /video is reading is never modified.
        canvas = frame.copy()
        for person in people:
            x1, y1, x2, y2 = person.box
            cv2.rectangle(canvas, (x1, y1), (x2, y2), BOX_COLOR, BOX_THICKNESS)
            cv2.circle(canvas, person.foot, DOT_RADIUS, FOOT_COLOR, -1)
        canvas = draw_zones(canvas, zones, counts)
        # A visible stamp, so a reviewer knows which alert and which video moment they are seeing.
        cv2.putText(canvas, f"ALERT {alert_id}  {now:.1f}s",
                    (10, canvas.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
                    cv2.LINE_AA)

        config.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"alert_{alert_id}.jpg"
        written = cv2.imwrite(str(config.EVIDENCE_DIR / filename), canvas,
                              [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY])
        if not written:
            return None
        return f"{config.EVIDENCE_URL_PREFIX}/{filename}"

    def _record_frame_time(self, elapsed: float) -> None:
        """Adds this frame's duration to the moving-average window.

        Why a moving average: one very slow frame (another program grabbing the CPU) would make
        an instant rate jump from 7 to 2 and back, which looks like a bug. Averaging the last
        FPS_WINDOW frames shows the real throughput.
        """
        self._frame_times.append(elapsed)
        if len(self._frame_times) > config.FPS_WINDOW:
            self._frame_times.pop(0)

    def measured_fps(self) -> float:
        """Returns frames per second from the moving average, or 0.0 before the first frame.

        Example: 20 frames in 2.8 s -> 20 / 2.8 ≈ 7.1 fps.
        """
        if not self._frame_times:
            return 0.0
        total = sum(self._frame_times)
        if total <= 0:
            return 0.0
        return len(self._frame_times) / total

    def _build_snapshot(self, zones: list[Zone], counts: dict[str, int], dwell: DwellTracker,
                        speeds: dict[int, float], grouped: dict[str, list],
                        now: float, peak_people: int,
                        debouncers: dict[str, AlertDebouncer],
                        active_alerts: dict[str, int], source_name: str,
                        new_alert: dict | None) -> dict:
        """Assembles the exact snapshot dict the dashboard contract describes.

        Why every number is cast to int/float: numpy scalars are not JSON-serialisable, and
        FastAPI would raise when a value like np.int64(7) reached the encoder. Casting here means
        the snapshot is plain JSON all the way out.

        Why speeds arrive as a track_id -> px/s map and grouped as zone -> people: the per-zone
        average needs both, and neither can be recovered from the counts alone.

        Example shape:
            {"ts": 31.5, "source": "crowded.mp4", "fps": 7.1, "total_people": 7,
             "peak_people": 9,
             "zones": [{"name": "Main Zone", "count": 7, "capacity": 4, "fill": 1.75,
                        "status": "OVER", "over_for": 3.2, "avg_dwell": 12.0,
                        "max_dwell": 24.0, "avg_speed": 18.4}],
             "alerts_active": 1, "new_alert": null}
        """
        zone_list = []
        for zone in zones:
            count = int(counts.get(zone.name, 0))
            capacity = int(zone.capacity)
            average, longest = dwell.stats(zone.name, now)
            # Average only over the people who actually have a speed this frame.
            zone_speeds = [speeds[person.track_id]
                           for person in grouped.get(zone.name, [])
                           if person.track_id in speeds]
            zone_list.append({
                "name": zone.name,
                "count": count,
                "capacity": capacity,
                # Guard against a zero capacity: a divide-by-zero would break the whole snapshot.
                "fill": float(count / capacity) if capacity else 0.0,
                "status": status_for(count, capacity),
                "over_for": float(debouncers[zone.name].over_for),
                "avg_dwell": float(average),
                "max_dwell": float(longest),
                "avg_speed": float(sum(zone_speeds) / len(zone_speeds)) if zone_speeds else 0.0,
            })

        return {
            "ts": float(now),
            "source": source_name,
            "fps": float(self.measured_fps()),
            "total_people": int(sum(counts.values())),
            "peak_people": int(peak_people),
            "zones": zone_list,
            "alerts_active": int(len(active_alerts)),
            # None on every frame except the one that fired an alert.
            "new_alert": new_alert,
        }

    # ---------- rendering for /video ----------

    def render(self, boxes: bool = True, zones_on: bool = True, heat: bool = True) -> bytes:
        """Builds one JPEG from the newest frame, drawing only what the flags ask for.

        Why flags instead of separate renderers: /video is polled with query parameters, so the
        browser can switch overlays on and off without restarting the engine or the stream.

        Why a copy first: the drawing calls all modify the image in place, and the frame inside
        SharedState must stay clean for the next request (and for the evidence photos).

        Returns raw JPEG bytes, ready to be written into an MJPEG part.

        Example: render(boxes=False, heat=False) sends the plain video with only zone polygons.
        """
        frame, people, snapshot = self.state.get()
        if frame is None:
            # Before the first frame exists, send a black image of the right size so the browser
            # has something to display instead of a broken image icon.
            canvas = np.zeros((360, config.FRAME_WIDTH, 3), dtype=np.uint8)
            cv2.putText(canvas, "starting engine...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (255, 255, 255), 2, cv2.LINE_AA)
            return self._encode(canvas)

        canvas = frame.copy()
        if heat:
            heat_layer = self.state.get_heat()
            if heat_layer is not None:
                colour, mask = heat_layer
                # Blend only where the mask is true, so cold pixels keep the clean video.
                if mask.any():
                    blended = canvas[mask].astype(np.float32)
                    tint = colour[mask].astype(np.float32)
                    alpha = config.HEAT_OVERLAY_ALPHA
                    canvas[mask] = (blended * (1.0 - alpha) + tint * alpha).astype(np.uint8)

        if boxes:
            for person in people:
                x1, y1, x2, y2 = person.box
                cv2.rectangle(canvas, (x1, y1), (x2, y2), BOX_COLOR, BOX_THICKNESS)
                cv2.circle(canvas, person.foot, DOT_RADIUS, FOOT_COLOR, -1)

        if zones_on:
            zone_objects, counts = self._zones_for_render(snapshot)
            if zone_objects:
                canvas = draw_zones(canvas, zone_objects, counts)

        return self._encode(canvas)

    def _zones_for_render(self, snapshot: dict) -> tuple[list[Zone], dict[str, int]]:
        """Rebuilds Zone objects and their counts for the current snapshot, using a per-clip cache.

        Why rebuild from the snapshot rather than hold Zones on self: the geometry lives in
        zones.json and the counts live in the snapshot. Reading them together means /video can
        never draw a stale polygon, for example right after auto_zones.py replaced the file.

        Why a cache: /video renders up to MJPEG_MAX_FPS frames a second, and re-parsing
        zones.json for each one is wasted work for data that rarely changes. The cache is keyed by
        clip, so switching source never reuses another camera's polygon.

        Why the try/except: if zones.json is being edited by hand while the server runs, a
        malformed file must not break the video stream - the overlay just disappears for a moment.
        """
        snapshot_source = snapshot.get("source")
        if not snapshot_source:
            return [], {}

        zones = self._zones_cache.get(snapshot_source)
        if zones is None:
            try:
                zones = load_zones(config.ZONES_FILE, snapshot_source)
            except SystemExit:
                return [], {}
            self._zones_cache[snapshot_source] = zones

        counts = {item["name"]: int(item["count"]) for item in snapshot.get("zones", [])}
        return zones, counts

    @staticmethod
    def _encode(canvas: np.ndarray) -> bytes:
        """Encodes one BGR frame as JPEG bytes at config.JPEG_QUALITY.

        Why a static method: it needs no engine state, and keeping it separate makes the encoder
        quality easy to find when the stream looks either blocky or too heavy.

        Example: a 640x360 frame at quality 80 is typically 25-60 KB.
        """
        ok, buffer = cv2.imencode(".jpg", canvas,
                                  [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buffer.tobytes()
