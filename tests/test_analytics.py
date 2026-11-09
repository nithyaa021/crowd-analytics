"""Tests for the three analytics classes, so a timing bug fails here instead of on stage.

Why these three groups: these classes are the only ones that remember things over time, and
time-based code is exactly where off-by-one-frame bugs hide. Each test uses small round numbers
(1 s, 3.4 s, 5 s) so a wrong answer is obvious without opening a debugger.

Run them with: .venv\\Scripts\\python.exe -m unittest -v
"""

import sys
import unittest
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app import config
from app.analytics import AlertDebouncer, DwellTracker, HeatmapAccumulator


class AlertDebouncerTests(unittest.TestCase):
    """Checks that the alert waits for a real problem and ignores a one-frame flicker."""

    def test_one_second_flicker_raises_nothing(self) -> None:
        """Capacity 5, one person too many for 1 s, then normal: 1 s < ON_DELAY 3 s, so no event.

        Why this matters: a detection that briefly double-counts a person must not page anybody.
        """
        debouncer = AlertDebouncer("Main Zone")
        # 0.5 s apart, as a 30 fps clip with STRIDE 2 would be: 0.0, 0.5, 1.0 are all over.
        events = [
            debouncer.update(now, 6, 5)
            for now in (0.0, 0.5, 1.0)
        ]
        # 1.5 s is back at capacity, so the run of 1.0 s is abandoned.
        events.append(debouncer.update(1.5, 5, 5))
        self.assertEqual([event for event in events if event], [])
        self.assertFalse(debouncer.active)

    def test_four_seconds_over_triggers_exactly_once(self) -> None:
        """Staying over capacity from 0 s to 4 s must give one TRIGGERED at the 3 s mark only.

        Why exactly once: the alert is a statement about an episode, not a message per frame.
        """
        debouncer = AlertDebouncer("Main Zone")
        events = [debouncer.update(now, 6, 5) for now in (0.0, 1.0, 2.0, 3.0, 3.5, 4.0)]
        triggered = [event for event in events if event == "TRIGGERED"]
        self.assertEqual(len(triggered), 1)
        # The event lands on the first sample that reaches ON_DELAY (3.0 s), not before it.
        self.assertEqual(events.index("TRIGGERED"), 3)
        self.assertTrue(debouncer.active)
        # 4.0 - 0.0 = 4.0 s of continuous over-capacity at the last call.
        self.assertAlmostEqual(debouncer.over_for, 4.0)

    def test_two_second_dip_does_not_clear(self) -> None:
        """After a trigger, 2 s back at capacity is less than OFF_DELAY 5 s, so the alert stays.

        Why: a crowd that briefly thins out and fills again is one continuous problem, and
        clearing and re-raising would spam the operator with two alerts for one episode.
        """
        debouncer = AlertDebouncer("Main Zone")
        for now in (0.0, 1.0, 2.0, 3.0):
            debouncer.update(now, 6, 5)
        self.assertTrue(debouncer.active)

        events = [debouncer.update(now, 5, 5) for now in (4.0, 5.0, 6.0)]
        self.assertEqual([event for event in events if event], [])
        self.assertTrue(debouncer.active)
        # Not over right now, so over_for reports zero even though the alert is still active.
        self.assertEqual(debouncer.over_for, 0.0)

    def test_five_seconds_under_clears_exactly_once(self) -> None:
        """After a trigger, 5 s at or below capacity gives exactly one CLEARED, then silence.

        Why exactly once: the CLEARED is the end of the episode; repeating it every frame would
        fill the log with noise.
        """
        debouncer = AlertDebouncer("Main Zone")
        for now in (0.0, 1.0, 2.0, 3.0):
            debouncer.update(now, 6, 5)
        self.assertTrue(debouncer.active)

        # Under capacity from 4.0 s; the clear happens at 9.0 s, which is 5.0 s later.
        events = [debouncer.update(now, 5, 5) for now in (4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)]
        cleared = [event for event in events if event == "CLEARED"]
        self.assertEqual(len(cleared), 1)
        self.assertEqual(events.index("CLEARED"), 5)
        self.assertFalse(debouncer.active)

    def test_over_for_is_zero_before_any_trouble(self) -> None:
        """A brand new debouncer reports 0 s over, so the dashboard can show it without a guard."""
        self.assertEqual(AlertDebouncer("Main Zone").over_for, 0.0)


class DwellTrackerTests(unittest.TestCase):
    """Checks that dwell time comes from the video clock and survives a missed detection."""

    def test_id_entering_at_nine_has_3_4_seconds_at_twelve_four(self) -> None:
        """ID 7 enters at 9.0 s; asked at 12.4 s, the answer is 12.4 - 9.0 = 3.4 and 3.4."""
        tracker = DwellTracker()
        tracker.update(9.0, {"Main Zone": [7]})
        average, maximum = tracker.stats("Main Zone", 12.4)
        self.assertAlmostEqual(average, 3.4)
        self.assertAlmostEqual(maximum, 3.4)

    def test_zone_with_nobody_returns_zero_pair(self) -> None:
        """An empty zone must answer (0, 0) so the UI can print 0.0 s without dividing by zero."""
        tracker = DwellTracker()
        tracker.update(9.0, {"Main Zone": [7]})
        self.assertEqual(tracker.stats("Empty Zone", 12.4), (0.0, 0.0))

    def test_id_missing_longer_than_grace_is_dropped(self) -> None:
        """A visitor not seen for more than TRACK_GRACE seconds must stop counting.

        Why: the tracker loses people when they leave the picture. Without this rule they would
        keep collecting dwell time forever and the average would climb all clip long.
        """
        tracker = DwellTracker()
        tracker.update(0.0, {"Main Zone": [7]})
        # Last seen at 0.0 s; wrap up at 1.0 s is still inside the 2.0 s grace window.
        tracker.update(1.0, {"Main Zone": []})
        self.assertGreater(tracker.stats("Main Zone", 1.0)[1], 0.0)

        # At 3.5 s the absence is 3.5 s, longer than TRACK_GRACE, so the entry is gone.
        tracker.update(3.5, {"Main Zone": []})
        self.assertEqual(tracker.stats("Main Zone", 3.5), (0.0, 0.0))

    def test_brief_miss_does_not_reset_the_clock(self) -> None:
        """One dropped frame must not restart the dwell time, which would under-report standing.

        Why: a person standing still is the easiest person for a detector to lose for a frame,
        and they are exactly the person whose dwell time matters most.
        """
        tracker = DwellTracker()
        tracker.update(0.0, {"Main Zone": [7]})
        tracker.update(0.5, {"Main Zone": []})   # missed once
        tracker.update(1.0, {"Main Zone": [7]})  # seen again, same ID
        # Still measured from 0.0 s, not from 1.0 s.
        self.assertAlmostEqual(tracker.stats("Main Zone", 1.0)[1], 1.0)

    def test_second_zone_starts_its_own_clock(self) -> None:
        """Walking from one zone into another starts the new zone at zero, not at the old value.

        Example: 10 s spent in Zone A, then 2 s in Zone B -> B reports 2.0 s, not 12.0 s.
        """
        tracker = DwellTracker()
        tracker.update(0.0, {"Zone A": [7]})
        tracker.update(10.0, {"Zone A": [], "Zone B": [7]})
        self.assertAlmostEqual(tracker.stats("Zone A", 10.0)[1], 0.0)
        self.assertAlmostEqual(tracker.stats("Zone B", 12.0)[1], 2.0)

    def test_average_and_max_differ_when_one_person_waits(self) -> None:
        """Two visitors of 1.0 s and 3.0 s must give (2.0, 3.0), which is why we report both.

        Why: the average says "2 s, all fine" while the maximum says "somebody has been stuck
        for 3 s". A bottleneck is about the worst case, not the middle one.
        """
        tracker = DwellTracker()
        tracker.update(0.0, {"Main Zone": [1]})
        tracker.update(2.0, {"Main Zone": [1, 2]})
        average, maximum = tracker.stats("Main Zone", 3.0)
        self.assertAlmostEqual(average, 2.0)
        self.assertAlmostEqual(maximum, 3.0)


class HeatmapAccumulatorTests(unittest.TestCase):
    """Checks that heat builds where people stand, fades with time, and draws only when hot."""

    def test_standing_three_frames_is_hotter_at_that_pixel(self) -> None:
        """Three hits at (40, 30) must leave more heat there than anywhere else.

        Why this is the core test: it is the whole promise of a heatmap - the warmest pixel is
        where people spent the most time, not where they happened to be last.
        """
        heatmap = HeatmapAccumulator(width=80, height=60)
        for _ in range(3):
            heatmap.add([(40, 30)])
        peak_row, peak_column = np.unravel_index(int(np.argmax(heatmap.heat)), heatmap.heat.shape)
        self.assertEqual((peak_column, peak_row), (40, 30))
        # A pixel nobody touched must be lower.
        self.assertGreater(heatmap.heat[30, 40], heatmap.heat[10, 20])

    def test_decay_lowers_old_heat(self) -> None:
        """With no new hits, heat must fall by HEAT_DECAY each frame.

        Example: 1.0 after 100 frames is 0.995 ** 100 ≈ 0.606, so the spot visibly cools.
        """
        heatmap = HeatmapAccumulator(width=20, height=20)
        heatmap.add([(5, 5)])
        first = float(heatmap.heat[5, 5])
        heatmap.add([])
        second = float(heatmap.heat[5, 5])
        self.assertAlmostEqual(second, first * config.HEAT_DECAY, places=6)
        self.assertLess(second, first)

    def test_points_outside_the_frame_are_clipped_not_dropped(self) -> None:
        """A foot at x = -3 must land on column 0 instead of crashing or vanishing.

        Why: the tracker occasionally reports a foot just outside the picture, and losing that
        person would make a busy frame look emptier than it was.
        """
        heatmap = HeatmapAccumulator(width=20, height=20)
        heatmap.add([(-3, 25)])
        # x = -3 clips to column 0, y = 25 clips to row 19, so the hit lands in the bottom-left.
        self.assertEqual(float(heatmap.heat[19, 0]), 1.0)

    def test_layer_returns_colour_image_and_mask(self) -> None:
        """layer() must give a 3-channel uint8 image plus a boolean mask of the hot areas.

        Why check the mask: the overlay uses it to protect the parts of the video that hold no
        heat, so a mask of the wrong type would either tint everything or tint nothing.
        """
        heatmap = HeatmapAccumulator(width=80, height=60)
        heatmap.add([(40, 30)])
        colour, mask = heatmap.layer()
        self.assertEqual(colour.shape, (60, 80, 3))
        self.assertEqual(colour.dtype, np.uint8)
        self.assertEqual(mask.shape, (60, 80))
        self.assertEqual(mask.dtype, bool)
        self.assertTrue(mask.any())
        # The far corner is cold, so it must not be painted.
        self.assertFalse(mask[0, 79])

    def test_empty_heatmap_gives_black_layer_and_empty_mask(self) -> None:
        """With no data, layer() must not divide by a zero peak (which would give NaN colours)."""
        heatmap = HeatmapAccumulator(width=40, height=30)
        colour, mask = heatmap.layer()
        self.assertFalse(mask.any())
        self.assertEqual(int(colour.max()), 0)

    def test_overlay_leaves_cold_pixels_untouched(self) -> None:
        """The overlay must change hot pixels and leave cold ones exactly as they were.

        Why: the video is the evidence. If the bottom of the frame is tinted for no reason, the
        viewer cannot tell heat from a video artefact.
        """
        heatmap = HeatmapAccumulator(width=80, height=60)
        heatmap.add([(40, 30)])
        frame = np.full((60, 80, 3), 100, dtype=np.uint8)
        blended = heatmap.overlay(frame, alpha=0.5)
        # A cold corner keeps its exact original value of 100 on every channel.
        self.assertEqual(blended[0, 79].tolist(), [100, 100, 100])
        # A hot pixel was blended, so at least one channel moved away from 100.
        self.assertNotEqual(blended[30, 40].tolist(), [100, 100, 100])
        # The original frame must survive, because callers still use it elsewhere.
        self.assertEqual(frame[30, 40].tolist(), [100, 100, 100])

    def test_reset_clears_every_pixel(self) -> None:
        """reset() must return the map to all zeros so the next clip starts clean."""
        heatmap = HeatmapAccumulator(width=20, height=20)
        heatmap.add([(5, 5)])
        heatmap.reset()
        self.assertEqual(float(heatmap.heat.max()), 0.0)


if __name__ == "__main__":
    unittest.main()
