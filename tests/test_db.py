"""Tests for the database layer, run against a temporary file so the real history is untouched.

Why these tests matter: db.py is the only module that persists anything. A wrong column order or
a missing NOT NULL would stay invisible until the dashboard chart was empty during a demo. Each
test uses its own throwaway database, so tests cannot influence each other or the real results/.

Run them with: .venv\\Scripts\\python.exe -m unittest -v
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db


class DatabaseTestCase(unittest.TestCase):
    """Gives every test a fresh database file that is deleted afterwards.

    Why a real file and not ":memory:": the production code opens a new connection per call, and
    an in-memory database would be empty for every call - the test would pass while the app broke.
    A temporary file on disk behaves exactly like results/crowd.db.
    """

    def setUp(self) -> None:
        """Creates a temporary folder and the two tables inside it."""
        self._folder = tempfile.TemporaryDirectory()
        self.db_path = Path(self._folder.name) / "test_crowd.db"
        db.init_db(self.db_path)

    def tearDown(self) -> None:
        """Removes the temporary folder, so a failed test leaves no files behind."""
        self._folder.cleanup()


class InitDbTests(DatabaseTestCase):
    """Checks that the schema exists and that creating it twice is harmless."""

    def test_tables_are_created(self) -> None:
        """After init_db, both tables must exist with the exact column names from the spec."""
        with db.connect(self.db_path) as connection:
            alerts = {row["name"] for row in connection.execute("PRAGMA table_info(alerts)")}
            headcount = {row["name"] for row in connection.execute("PRAGMA table_info(headcount)")}

        self.assertEqual(alerts, {"id", "zone", "source", "started_at", "video_ts", "ended_at",
                                 "peak_count", "capacity", "keyframe"})
        self.assertEqual(headcount, {"ts", "zone", "count"})

    def test_init_is_idempotent(self) -> None:
        """Calling init_db twice must not wipe the rows the first run's users created.

        Why: the server calls init_db on every restart, so a destructive version would silently
        delete the whole alert history each time the app was started.
        """
        alert_id = db.insert_alert("Main Zone", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.db_path)
        db.init_db(self.db_path)
        self.assertEqual(len(db.list_alerts(db_path=self.db_path)), 1)
        self.assertEqual(db.list_alerts(db_path=self.db_path)[0]["id"], alert_id)


class AlertTests(DatabaseTestCase):
    """Checks the alert lifecycle: insert, raise the peak, end, and read back."""

    def test_insert_returns_an_increasing_id(self) -> None:
        """The first two alerts must get ids 1 and 2, because the evidence file names use them."""
        first = db.insert_alert("Main Zone", "crowded.mp4", 10.0, 6, 4, None,
                                db_path=self.db_path)
        second = db.insert_alert("Main Zone", "crowded.mp4", 40.0, 9, 4, None,
                                 db_path=self.db_path)
        self.assertEqual((first, second), (1, 2))

    def test_new_alert_is_open(self) -> None:
        """A freshly inserted alert must have ended_at None, or the dashboard would hide it."""
        alert_id = db.insert_alert("Main Zone", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.db_path)
        alert = db.list_alerts(db_path=self.db_path)[0]
        self.assertEqual(alert["id"], alert_id)
        self.assertIsNone(alert["ended_at"])
        self.assertEqual(alert["peak_count"], 7)
        self.assertEqual(alert["capacity"], 4)

    def test_update_peak_only_raises(self) -> None:
        """A lower count must never reduce a peak that a busier frame already recorded.

        Example: peak 7, then a count of 5 leaves 7; a count of 9 becomes 9.
        """
        alert_id = db.insert_alert("Main Zone", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.db_path)
        db.update_peak(alert_id, 5, db_path=self.db_path)
        self.assertEqual(db.list_alerts(db_path=self.db_path)[0]["peak_count"], 7)
        db.update_peak(alert_id, 9, db_path=self.db_path)
        self.assertEqual(db.list_alerts(db_path=self.db_path)[0]["peak_count"], 9)

    def test_end_alert_stamps_the_time_and_keeps_the_row(self) -> None:
        """Ending an alert must keep it in the history; the crowd being gone is the point of history."""
        alert_id = db.insert_alert("Main Zone", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.db_path)
        db.end_alert(alert_id, "2026-11-09T14:04:02+00:00", db_path=self.db_path)
        alert = db.list_alerts(db_path=self.db_path)[0]
        self.assertEqual(alert["ended_at"], "2026-11-09T14:04:02+00:00")
        self.assertEqual(alert["peak_count"], 7)

    def test_set_keyframe_stores_the_photo_url(self) -> None:
        """The evidence URL must come back exactly as stored, because the browser fetches it."""
        alert_id = db.insert_alert("Main Zone", "crowded.mp4", 31.5, 7, 4, None,
                                   db_path=self.db_path)
        db.set_keyframe(alert_id, "/evidence/alert_1.jpg", db_path=self.db_path)
        self.assertEqual(db.list_alerts(db_path=self.db_path)[0]["keyframe"],
                         "/evidence/alert_1.jpg")

    def test_list_alerts_is_newest_first_and_respects_the_limit(self) -> None:
        """Three alerts with limit 2 must return ids 3 then 2, not 1 then 2."""
        for index in range(3):
            db.insert_alert("Main Zone", "crowded.mp4", float(index), 6, 4, None,
                            db_path=self.db_path)
        alerts = db.list_alerts(limit=2, db_path=self.db_path)
        self.assertEqual([alert["id"] for alert in alerts], [3, 2])

    def test_a_zone_name_with_a_quote_is_stored_safely(self) -> None:
        """A name containing an apostrophe must round-trip, proving queries are parameterised.

        Why: this is the injection test. With string formatting into SQL this name would break
        the statement (or worse); with a ? parameter it is just text.
        """
        awkward = "Main Zone's door"
        alert_id = db.insert_alert(awkward, "crowded.mp4", 10.0, 6, 4, None,
                                   db_path=self.db_path)
        self.assertEqual(db.list_alerts(db_path=self.db_path)[0]["zone"], awkward)
        self.assertEqual(alert_id, 1)


class HeadcountTests(DatabaseTestCase):
    """Checks the head-count history the line chart reads."""

    def test_rows_come_back_oldest_first(self) -> None:
        """A chart plots left to right in time order, so the API must not have to sort."""
        # Timestamps are relative to now, because headcount_since() filters on the wall clock and
        # a hard-coded date would fall outside the window as soon as the test was written.
        now = datetime.now(timezone.utc)
        older = (now - timedelta(seconds=4)).isoformat()
        newer = (now - timedelta(seconds=2)).isoformat()
        db.add_headcount(older, "Main Zone", 3, db_path=self.db_path)
        db.add_headcount(newer, "Main Zone", 7, db_path=self.db_path)
        rows = db.headcount_since(10, db_path=self.db_path)
        self.assertEqual([row["count"] for row in rows], [3, 7])

    def test_old_rows_are_excluded(self) -> None:
        """A sample from an hour ago must not appear in a 10-minute window.

        Why: the chart would otherwise stretch its x-axis over the whole history and show a flat
        line at the right for the interesting part.
        """
        db.add_headcount("2020-01-01T00:00:00+00:00", "Main Zone", 99, db_path=self.db_path)
        db.add_headcount(db.utc_now_iso(), "Main Zone", 4, db_path=self.db_path)
        rows = db.headcount_since(10, db_path=self.db_path)
        self.assertEqual([row["count"] for row in rows], [4])

    def test_a_zero_count_is_stored_not_dropped(self) -> None:
        """An empty zone must still produce a row, otherwise the chart shows gaps, not quiet.

        Why: dropping zeros makes "nobody here" indistinguishable from "no data yet".
        """
        db.add_headcount(db.utc_now_iso(), "Main Zone", 0, db_path=self.db_path)
        rows = db.headcount_since(10, db_path=self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 0)


if __name__ == "__main__":
    unittest.main()
