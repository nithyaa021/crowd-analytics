"""Tests for the whole pipeline: zones, analytics, the database and the shared state.

Why one file instead of six: the project is graded on being explainable, and one test file that
reads top to bottom in the same order as the data flows (person -> zone -> analytics -> database)
is easier to walk a panel through than six files they have to open one by one.

Run: .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app import db
from app.analytics import AlertDebouncer, DwellTracker, HeatmapAccumulator, SpeedTracker
from app.engine import SharedState, empty_snapshot, list_clips
from app.vision import foot_point, resize_frame
from app.zones import make_polygon, status_for, zone_of
from app.vision import Person
import numpy as np


class TestFootPoint(unittest.TestCase):
    """The foot point is the whole geometry system's foundation, so it is checked first."""

    def test_foot_is_bottom_centre(self):
        """Why: a box's centre floats at chest height; zones are drawn on the floor."""
        # Box (100, 50) to (140, 200): centre x = 120, bottom y = 200.
        self.assertEqual(foot_point((100, 50, 140, 200)), (120, 200))


class TestResize(unittest.TestCase):
    """Resizing keeps the aspect ratio, so people are never stretched."""

    def test_keeps_aspect_ratio(self):
        """Why: 1280x720 shrunk to 640 wide must be 360 high, not 720."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        resized = resize_frame(frame, 640)
        self.assertEqual(resized.shape[:2], (360, 640))

    def test_rejects_zero_width(self):
        """Why: a zero width would make every coordinate meaningless."""
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            resize_frame(frame, 0)


class TestZones(unittest.TestCase):
    """Zone lookup and the status rule, with the numeric examples from the docs."""

    def test_zone_of_inside_and_outside(self):
        """Why: a foot inside the square is counted, one outside is not."""
        # A 10x10 square from (10, 10) to (20, 20).
        polygon = make_polygon([(10, 10), (20, 10), (20, 20), (10, 20)])

        class FakeZone:
            """Minimal stand-in so the test does not need a name or capacity."""

            name = "test"
            capacity = 1

        zone = FakeZone()
        zone.polygon = polygon
        self.assertIs(zone_of([zone], (15, 15)), zone)
        self.assertIsNone(zone_of([zone], (50, 50)))

    def test_status_thresholds(self):
        """Why: the colour and the alert must come from one rule, not two guesses."""
        # Capacity 10: 7 -> OK, 8 -> NEAR, 10 -> NEAR, 11 -> OVER.
        self.assertEqual(status_for(7, 10), "OK")
        self.assertEqual(status_for(8, 10), "NEAR")
        self.assertEqual(status_for(10, 10), "NEAR")
        self.assertEqual(status_for(11, 10), "OVER")


class TestDwell(unittest.TestCase):
    """Dwell answers "how long has this person been standing here?"."""

    def test_dwell_grows_with_time(self):
        """Why: admitted at 9.0 s and asked at 12.4 s, the visit is 3.4 s old."""
        tracker = DwellTracker()
        tracker.update(9.0, {"Main": [7]})
        average, longest = tracker.stats("Main", 12.4)
        self.assertAlmostEqual(average, 3.4)
        self.assertAlmostEqual(longest, 3.4)

    def test_departed_person_is_forgotten(self):
        """Why: a visitor who left must not keep collecting dwell time forever."""
        tracker = DwellTracker()
        tracker.update(0.0, {"Main": [7]})
        # TRACK_GRACE is 2 s, so at 10 s the entry must be gone.
        tracker.update(10.0, {"Main": []})
        self.assertEqual(tracker.stats("Main", 10.0), (0.0, 0.0))


class TestSpeed(unittest.TestCase):
    """Speed answers "are people walking through, or stuck?"."""

    def test_first_sighting_has_no_speed(self):
        """Why: one position cannot be divided by time, so no speed is reported yet."""
        tracker = SpeedTracker()
        person = _person(track_id=1, foot=(100, 200))
        self.assertEqual(tracker.update(1.0, [person]), {})

    def test_second_sighting_reports_pixels_per_second(self):
        """Why: 40 px moved in 2 s is 20 px/s, the number the gauge shows."""
        tracker = SpeedTracker()
        tracker.update(1.0, [_person(track_id=1, foot=(100, 200))])
        speeds = tracker.update(3.0, [_person(track_id=1, foot=(140, 200))])
        self.assertAlmostEqual(speeds[1], 20.0)


class TestDebouncer(unittest.TestCase):
    """The debouncer is what stops one crowd producing dozens of alerts."""

    def test_short_spike_does_not_trigger(self):
        """Why: a 1 s blip above capacity is a detection artefact, not a crowd."""
        debouncer = AlertDebouncer("Main")
        events = [debouncer.update(t, 6, 5) for t in (0.0, 0.5, 1.0)]
        self.assertEqual(events, [None, None, None])

    def test_sustained_over_capacity_triggers_once(self):
        """Why: 4 s above capacity is one real problem and must raise exactly one alert."""
        debouncer = AlertDebouncer("Main")
        events = [debouncer.update(t, 6, 5) for t in (0.0, 1.0, 2.0, 3.0, 4.0)]
        # ON_DELAY is 3 s, so the 3.0 s call fires and the 4.0 s call stays quiet.
        self.assertEqual(events, [None, None, None, "TRIGGERED", None])

    def test_clears_after_off_delay(self):
        """Why: an alert must not flicker off the moment one person steps out."""
        debouncer = AlertDebouncer("Main")
        debouncer.update(0.0, 6, 5)
        debouncer.update(3.0, 6, 5)          # fires, because 3 s over capacity >= ON_DELAY
        # The under-capacity run starts at 4.0 s, so OFF_DELAY (5 s) is reached at 9.0 s.
        self.assertIsNone(debouncer.update(4.0, 4, 5))
        self.assertIsNone(debouncer.update(8.0, 4, 5))   # only 4 s under, not enough
        self.assertEqual(debouncer.update(9.0, 4, 5), "CLEARED")


class TestHeatmap(unittest.TestCase):
    """The heatmap is the "where do people stand?" layer."""

    def test_empty_heatmap_draws_nothing(self):
        """Why: before anyone appears the overlay must be invisible, not a blue wash."""
        heatmap = HeatmapAccumulator(10, 10)
        _colour, mask = heatmap.layer()
        self.assertFalse(mask.any())

    def test_point_raises_heat_there(self):
        """Why: one foot point must produce one hot pixel, at that pixel."""
        heatmap = HeatmapAccumulator(10, 10)
        heatmap.add([(5, 7)])
        self.assertGreater(heatmap.heat[7, 5], 0.0)
        self.assertEqual(heatmap.heat[0, 0], 0.0)


class TestDatabase(unittest.TestCase):
    """The history survives a restart and is never rewritten by a lower peak."""

    def setUp(self):
        """Why a temporary folder: a test must never touch the real results/crowd.db."""
        self._folder = TemporaryDirectory()
        self.database = Path(self._folder.name) / "test.db"
        db.init_db(self.database)

    def tearDown(self):
        """Removes the temporary database so repeated runs start clean."""
        self._folder.cleanup()

    def test_alert_round_trip(self):
        """Why: an inserted alert must read back with the id the engine needs for the photo."""
        alert_id = db.insert_alert("Main", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.database)
        self.assertEqual(alert_id, 1)
        alerts = db.list_alerts(db_path=self.database)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["peak_count"], 7)

    def test_peak_never_lowers(self):
        """Why: the busiest moment is the evidence, so a quiet frame must not erase it."""
        alert_id = db.insert_alert("Main", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.database)
        db.update_peak(alert_id, 5, db_path=self.database)
        self.assertEqual(db.list_alerts(db_path=self.database)[0]["peak_count"], 7)
        db.update_peak(alert_id, 9, db_path=self.database)
        self.assertEqual(db.list_alerts(db_path=self.database)[0]["peak_count"], 9)

    def test_headcount_history(self):
        """Why: the chart needs samples in time order, oldest first."""
        # Use the real clock: headcount_since keeps only the last N minutes, so a fixed date
        # would fall outside the window as soon as the system date moves past it.
        first = db.utc_now_iso()
        db.add_headcount(first, "Main", 3, db_path=self.database)
        db.add_headcount(first, "Main", 5, db_path=self.database)
        rows = db.headcount_since(60, db_path=self.database)
        self.assertEqual([row["count"] for row in rows], [3, 5])


class TestSharedState(unittest.TestCase):
    """The hand-over between the video thread and the web thread."""

    def test_empty_snapshot_is_well_formed(self):
        """Why: the browser connects before the first frame, so the shape must exist already."""
        snapshot = empty_snapshot("crowded.mp4")
        self.assertEqual(snapshot["total_people"], 0)
        self.assertEqual(snapshot["zones"], [])

    def test_get_returns_a_copy_of_the_frame(self):
        """Why: the engine keeps drawing over its own buffer; a shared reference would tear."""
        state = SharedState()
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        state.set(frame=frame)
        frame[:] = 255
        stored, _, _ = state.get()
        self.assertEqual(int(stored[0, 0, 0]), 0)


class TestClips(unittest.TestCase):
    """The source allow-list is also the security boundary for POST /api/source."""

    def test_clips_are_plain_mp4_names(self):
        """Why: a name with a path separator could escape demo_videos."""
        for name in list_clips():
            self.assertTrue(name.endswith(".mp4"))
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)


def _person(track_id: int, foot: tuple[int, int]) -> Person:
    """Builds a Person for the analytics tests without needing a real detection.

    Why a helper: the analytics classes only read track_id and foot, so a fake person keeps the
    tests fast and free of YOLO, which would take a second per test to load.
    """
    return Person(track_id=track_id, box=(0, 0, 10, 10), conf=0.9, foot=foot)


if __name__ == "__main__":
    unittest.main()
