"""Turns per-frame person positions into the three numbers the dashboard shows.

Why this file exists: counting people per frame is easy, but the interesting answers need
memory over time - "how long has this person been standing here?", "where do crowds keep
forming?", and "has this zone really been full for 3 seconds, or did it just flicker?".
Each question is one small class below, so each can be tested on its own.

Every time value that enters this file is a VIDEO timestamp in seconds (for example
frame_index / fps). Nothing here calls time.time(), because the demo replays a recording: a
wall clock would make the dwell times and the alert timings meaningless.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from app import config


def _odd(value: int) -> int:
    """Returns the nearest odd number at or above value.

    Why: Gaussian blur refuses an even kernel size, so a computed 32 would raise an error.
    Making it odd here means callers can pass any width without thinking about it.

    Example: 32 -> 33, 33 -> 33, 34 -> 35.
    """
    return value if value % 2 == 1 else value + 1


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Returns the straight-line distance between two (x, y) points, in pixels.

    Why Pythagoras and not |dx| + |dy|: a diagonal step is genuinely shorter than walking its two
    sides, and adding the sides would overstate speed for anyone moving at an angle.

    Example: (0, 0) to (30, 40) -> sqrt(900 + 1600) = 50 px.
    """
    return float(np.hypot(second[0] - first[0], second[1] - first[1]))


@dataclass
class _DwellEntry:
    """One remembered visit: when this track ID first entered a zone, and when it was last seen.

    Why two times: entered_at answers "how long have they been here?", and last_seen is what
    tells update() that someone has left and should be forgotten.
    """

    entered_at: float
    last_seen: float


class DwellTracker:
    """Remembers when each tracked person entered each zone, so we can report how long they stay.

    Why per (zone, track_id) and not per track_id: one person can walk from a quiet zone into a
    busy one, and the second zone's dwell must start when they cross the line - not when they
    first appeared on screen.

    Example: ID 7 appears in "Main Zone" at video time 9.0 s. At 12.4 s the zone's average dwell
    is 3.4 s, because 12.4 - 9.0 = 3.4.
    """

    def __init__(self) -> None:
        """Starts with nobody remembered, which is the correct state for a clip's first frame."""
        self._entries: dict[tuple[str, int], _DwellEntry] = {}

    def update(self, now: float, members: dict[str, list[int]]) -> None:
        """Records who is inside each zone right now and forgets people who left long ago.

        Why called every processed frame: it is the only moment we learn that someone is still
        there. An ID that stops appearing is not deleted immediately, because a missed detection
        for a frame or two is normal and would otherwise reset the dwell time to zero.

        Example: members {"Main Zone": [7, 9]} at 9.0 s starts two entries; the same call at
        9.5 s only refreshes their last_seen times.
        """
        for zone_name, track_ids in members.items():
            for track_id in track_ids:
                key = (zone_name, track_id)
                entry = self._entries.get(key)
                if entry is None:
                    # First time we see this visitor in this zone: their clock starts now.
                    self._entries[key] = _DwellEntry(entered_at=now, last_seen=now)
                else:
                    # A returning visitor keeps the original entry time, so dwell is not reset.
                    entry.last_seen = now

        # Forget anyone not seen for longer than TRACK_GRACE seconds in that zone.
        self._entries = {
            key: entry
            for key, entry in self._entries.items()
            if now - entry.last_seen <= config.TRACK_GRACE
        }

    def stats(self, zone_name: str, now: float) -> tuple[float, float]:
        """Returns (average dwell, longest dwell) in seconds for one zone, or (0, 0) if empty.

        Why both numbers: an average alone hides a bottleneck - one person waiting 60 s among
        nine people waiting 2 s is a different situation from ten people waiting 8 s each, yet
        both average about 8 s. The maximum exposes the person who is actually stuck.

        Dwell is measured to `now`, not to the last time the person was seen, because the person
        is still standing there - the detector just missed a frame. Anyone who leaves for longer
        than TRACK_GRACE is already forgotten by update(), so a departed person cannot keep
        collecting time.

        Example: one entry started at 9.0 s, asked at 12.4 s, gives (3.4, 3.4); with nobody
        remembered it gives (0, 0).
        """
        durations = [
            now - entry.entered_at
            for (name, _track_id), entry in self._entries.items()
            if name == zone_name
        ]
        if not durations:
            return (0.0, 0.0)
        return (sum(durations) / len(durations), max(durations))

    def reset(self) -> None:
        """Forgets every visit, which is needed when we switch to another clip.

        Why: without this, the next clip would inherit the previous clip's track IDs and report
        dwell times measured from a completely different video.
        """
        self._entries.clear()


class SpeedTracker:
    """Estimates how fast each tracked person is moving, in pixels per second.

    Why pixels and not km/h: turning pixels into metres needs a camera calibration - where the
    floor is, how far away it sits, and at what angle. We do not have that, so any km/h figure
    would be invented. Pixels per second is honest, needs no extra data, and is still comparable
    inside one clip: a zone where people move at 5 px/s is far more congested than one where they
    move at 40 px/s, which is exactly the operational question.

    Example: a foot point at (100, 200) at video time 1.0 s, then at (140, 200) at 3.0 s. The
    distance is 40 px, the elapsed time is 2 s, so the speed is 20 px/s.
    """

    def __init__(self) -> None:
        """Starts remembering nobody, which is the correct state for a clip's first frame."""
        self._last: dict[int, tuple[float, tuple[float, float]]] = {}

    def update(self, now: float, people: list) -> dict[int, float]:
        """Records where everyone is now and returns the speed of whoever moved since last time.

        Why it returns a dict instead of storing the answer: the caller needs the speeds for this
        frame's snapshot, and a person seen for the first time has no earlier position, so it is
        simply absent from the result rather than reported as a false 0 px/s.

        Why people is typed as a plain list: this module only reads .track_id and .foot from each
        entry, so it stays usable with the real Person dataclass and with test doubles.

        Example: update(1.0, [ID 7 at (100, 200)]) returns {}, and update(3.0, [ID 7 at
        (140, 200)]) returns {7: 20.0}.
        """
        speeds: dict[int, float] = {}
        # Carry over who was seen before, so a single missed detection does not reset the speed.
        seen_now = dict(self._last)

        for person in people:
            track_id = int(person.track_id)
            foot = (float(person.foot[0]), float(person.foot[1]))

            previous = self._last.get(track_id)
            # A first sighting has nothing to compare against, so no speed is reported yet.
            if previous is not None:
                previous_time, previous_foot = previous
                elapsed = now - previous_time
                # Two detections in the same instant would divide by zero; skip rather than crash.
                if elapsed > 0:
                    speeds[track_id] = _distance(previous_foot, foot) / elapsed

            seen_now[track_id] = (now, foot)

        # Forget anyone unseen for longer than TRACK_GRACE, so the dict cannot grow forever.
        self._last = {
            track_id: entry
            for track_id, entry in seen_now.items()
            if now - entry[0] <= config.TRACK_GRACE
        }
        return speeds

    def reset(self) -> None:
        """Forgets every remembered position, which is needed when we switch to another clip.

        Why: track IDs restart at 1 for a new clip, so a remembered position from the old clip
        would produce a huge fake speed the first time ID 1 reappears.
        """
        self._last.clear()


class HeatmapAccumulator:
    """Builds a "where do people stand?" picture by piling up foot points over time.

    Why decay: a plain total would make one busy minute look hot forever, so a spot that was
    crowded ten minutes ago would still glow. Multiplying by HEAT_DECAY every frame lets old
    heat fade, which means the picture always describes the recent past.

    Example with HEAT_DECAY 0.995: a pixel holding 1.0 falls to 0.995 after one frame, about
    0.951 after ten frames, and about 0.61 after one hundred frames.
    """

    def __init__(self, width: int, height: int) -> None:
        """Creates an empty heat image the same size as the frames we will overlay it on.

        Why width and height in that order: it matches every other OpenCV/numpy call in this
        project (array shape is height first), and passing them explicitly stops a caller from
        accidentally reusing a stale frame size after a resize.
        """
        if width < 1 or height < 1:
            raise ValueError("heatmap width and height must be at least 1 pixel")
        self.width = int(width)
        self.height = int(height)
        # float32, not uint8: 0.995 * 255 would round down every frame and lose the heat.
        self.heat = np.zeros((self.height, self.width), dtype=np.float32)

    def add(self, points: list[tuple[int, int]]) -> None:
        """Fades the whole map a little, then adds 1.0 at every foot point given.

        Why clip instead of skip: a tracker can briefly report a foot one pixel outside the
        frame. Skipping the point would silently lose a person; clamping keeps the evidence and
        cannot corrupt the array.

        Example: a pixel at 1.0 with one point on it becomes 1.0 * 0.995 + 1 = 1.995.
        """
        self.heat *= config.HEAT_DECAY
        for x, y in points:
            # Clamp to the valid pixel range so an out-of-frame foot cannot raise IndexError.
            column = min(max(int(x), 0), self.width - 1)
            row = min(max(int(y), 0), self.height - 1)
            self.heat[row, column] += 1.0

    def layer(self) -> tuple[np.ndarray, np.ndarray]:
        """Builds the colour heat image and a mask saying which pixels are worth drawing.

        Why blur: one foot point is a single pixel, which is invisible on a video. Blurring
        turns it into a soft blob, and overlapping blobs become a visible hot area.

        Why normalise: the raw values depend on how long the clip has run, so they could be 2 or
        200. Dividing by the current maximum makes the colours mean "hot compared with now",
        which is what a viewer expects from a heatmap.

        Why the mask: without it the whole frame would be tinted blue, including empty floor,
        and the video underneath would be hard to read.

        Returns (colour_image, mask) where mask is a boolean array of the same size.

        Example: values 0.0, 0.5, 2.0 normalise to 0, 64, 255; with HEAT_MASK_RATIO 0.08 only
        the last two pass the mask (64 >= 20).
        """
        # An empty map has no maximum to divide by, so return a black layer and an empty mask.
        peak = float(self.heat.max())
        if peak <= 0.0:
            black = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            return black, np.zeros((self.height, self.width), dtype=bool)

        kernel = _odd(max(3, round(self.width * config.HEAT_BLUR_FRACTION)))
        blurred = cv2.GaussianBlur(self.heat, (kernel, kernel), 0)

        # Scale to 0..255 using this frame's own peak, so the colours always span the full range.
        blurred_peak = float(blurred.max())
        if blurred_peak <= 0.0:
            black = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            return black, np.zeros((self.height, self.width), dtype=bool)
        normalised = np.clip(blurred / blurred_peak, 0.0, 1.0)
        grey = (normalised * 255).astype(np.uint8)

        colour = cv2.applyColorMap(grey, cv2.COLORMAP_JET)
        mask = normalised >= config.HEAT_MASK_RATIO
        return colour, mask

    def overlay(self, frame: np.ndarray, alpha: float = config.HEAT_OVERLAY_ALPHA) -> np.ndarray:
        """Blends the heat colours onto a copy of the frame, only where the mask is true.

        Why a copy: the caller still needs the clean frame for detection and for saving, and
        painting heat into it would feed our own colours back into the next frame.

        Why only inside the mask: outside it the frame is untouched, so people and zone borders
        stay sharp and the heat reads as an extra layer rather than a filter over everything.

        Example with alpha 0.5: a frame pixel (100, 100, 100) under a red heat pixel
        (0, 0, 255) becomes about (50, 50, 178).
        """
        colour, mask = self.layer()
        blended = frame.copy()
        if not mask.any():
            return blended
        # np.where with a per-pixel mask does the "only where hot" blend in one numpy step.
        hot = blended[mask].astype(np.float32)
        tint = colour[mask].astype(np.float32)
        blended[mask] = (hot * (1.0 - alpha) + tint * alpha).astype(np.uint8)
        return blended

    def reset(self) -> None:
        """Clears all accumulated heat, so the next clip starts with a clean map.

        Why: heat is evidence about one camera view. Carrying it into the next clip would draw
        hot spots in places nobody has stood in that video.
        """
        self.heat[:] = 0.0


class AlertDebouncer:
    """Turns a raw head count into at most one alert per over-capacity episode.

    Why this exists: the count jumps up and down by one person constantly (a detection misses,
    a person steps on a line). Alerting on every frame above capacity would produce dozens of
    alerts for one real problem. This class only fires after the zone has been over capacity for
    ON_DELAY seconds, and only clears after it has been back to normal for OFF_DELAY seconds.

    Example with ON_DELAY 3 s and capacity 5: counts over 6 that last 1 s produce nothing;
    the same counts lasting 4 s produce exactly one TRIGGERED, however many frames pass.
    """

    def __init__(self, name: str = "") -> None:
        """Starts inactive, with no over-capacity run in progress.

        Why keep a name: the demo prints several debouncers' events in one log, and a bare
        "TRIGGERED" would not say which zone it belongs to.
        """
        self.name = name
        self.active = False
        # When the current over-capacity run started, or None if we are not over right now.
        self._over_since: float | None = None
        # When the current at-or-below-capacity run started, or None if we are over.
        self._under_since: float | None = None
        # Last time we were updated, so over_for can answer without another argument.
        self._last_now: float = 0.0

    @property
    def over_for(self) -> float:
        """Seconds the current over-capacity run has lasted, or 0.0 when not over.

        Why expose it: the dashboard shows "over for 4.1 s", which tells an operator whether an
        alert is about to fire, rather than just showing a count.
        """
        if self._over_since is None:
            return 0.0
        # max() guards against a caller passing a timestamp that goes slightly backwards.
        return max(0.0, self._last_now - self._over_since)

    def update(self, now: float, count: int, capacity: int) -> str | None:
        """Feeds one frame's count in, and returns "TRIGGERED", "CLEARED" or None.

        Why time-based runs instead of counting frames: STRIDE means frames are not equally
        spaced in seconds, so counting frames would make a 3-second delay last 3 frames.

        Why the run start is remembered instead of adding up deltas: if the caller skips frames
        (or the video jumps), the elapsed time is still exactly now - run_start. Summing deltas
        silently loses the gap.

        Example: over at 0 s, 1 s, 2 s, 3 s -> the 3 s call returns TRIGGERED, the 4 s call
        returns None because the alert is already active.
        """
        self._last_now = now
        if count > capacity:
            if self._over_since is None:
                self._over_since = now
            # Any time spent under capacity is irrelevant once we are over again.
            self._under_since = None
            if not self.active and now - self._over_since >= config.ON_DELAY:
                self.active = True
                return "TRIGGERED"
            return None

        if self._under_since is None:
            self._under_since = now
        # Being back at capacity cancels the over-capacity run, so a later run starts from zero.
        self._over_since = None
        if self.active and now - self._under_since >= config.OFF_DELAY:
            self.active = False
            return "CLEARED"
        return None

    def reset(self) -> None:
        """Returns the debouncer to its fresh state, for reuse between clips.

        Why: a new clip has different track IDs and a different crowd, so an alert left active
        from the previous clip would clear itself in the wrong video.
        """
        self.active = False
        self._over_since = None
        self._under_since = None
        self._last_now = 0.0
