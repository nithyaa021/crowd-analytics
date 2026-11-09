"""Tests for the zone rules, so a wrong colour or a missed person fails here, not on stage.

Why these three groups: every later step (video demo, API, alerts, database) depends on
status_for, zone_of and load_zones. If those three are right, the rest is wiring.

Run them with: .venv\\Scripts\\python.exe -m unittest -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.zones import Zone, load_zones, make_polygon, status_for, zone_of

# A simple 100x100 square, far easier to reason about than a real zone.
SQUARE = [(100, 100), (200, 100), (200, 200), (100, 200)]


class StatusForTests(unittest.TestCase):
    """Checks the OK / NEAR / OVER boundary with a capacity of 10."""

    def test_seven_of_ten_is_ok(self) -> None:
        """7 is below 0.8 * 10 = 8, so the zone is simply fine."""
        self.assertEqual(status_for(7, 10), "OK")

    def test_eight_of_ten_is_near(self) -> None:
        """8 is exactly the warning line, and the rule is ">= NEAR_RATIO", so NEAR."""
        self.assertEqual(status_for(8, 10), "NEAR")

    def test_exactly_full_is_near_not_over(self) -> None:
        """10 of 10 is full but not over; only 11 counts as OVER. This is the important edge."""
        self.assertEqual(status_for(10, 10), "NEAR")

    def test_eleven_of_ten_is_over(self) -> None:
        """One person too many is the first OVER, so the alert can fire at a clear moment."""
        self.assertEqual(status_for(11, 10), "OVER")


class ZoneOfTests(unittest.TestCase):
    """Checks the point-in-polygon answer for a 100..200 square."""

    def setUp(self) -> None:
        """Builds one zone per test so no test can change another test's polygon."""
        self.zone = Zone(name="Main Zone", capacity=5, polygon=make_polygon(SQUARE))

    def test_point_inside(self) -> None:
        """(150, 150) sits in the middle of the square, so it must find the zone."""
        self.assertIs(zone_of([self.zone], (150, 150)), self.zone)

    def test_point_outside(self) -> None:
        """(50, 50) is diagonally outside the square, so the answer is None."""
        self.assertIsNone(zone_of([self.zone], (50, 50)))

    def test_point_on_the_edge_counts_as_inside(self) -> None:
        """(100, 150) is on the left edge; OpenCV returns 0 there and we treat >= 0 as inside.

        Why it matters: a person walking along the painted line should not flicker in and out
        of the count from frame to frame.
        """
        self.assertIs(zone_of([self.zone], (100, 150)), self.zone)


class LoadZonesTests(unittest.TestCase):
    """Checks that a missing clip entry is a clear error, not a silent empty list."""

    def test_load_reads_a_known_clip(self) -> None:
        """A clip that exists must come back with its name, capacity and polygon shape."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "zones.json"
            path.write_text(json.dumps({"demo.mp4": [
                {"name": "Main Zone", "capacity": 4, "polygon": SQUARE}
            ]}), encoding="utf-8")
            zones = load_zones(path, "demo.mp4")
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].name, "Main Zone")
        self.assertEqual(zones[0].capacity, 4)
        # The (N, 1, 2) shape is what cv2.pointPolygonTest expects.
        self.assertEqual(zones[0].polygon.shape, (4, 1, 2))

    def test_unknown_clip_raises_a_clear_error(self) -> None:
        """The error must name the clip and point at scripts/auto_zones.py, so the fix is obvious."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "zones.json"
            path.write_text(json.dumps({"other.mp4": []}), encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                load_zones(path, "missing.mp4")
        message = str(caught.exception)
        self.assertIn("missing.mp4", message)
        # Path separators differ on Windows, so only the file name is checked here.
        self.assertIn("auto_zones.py", message)


if __name__ == "__main__":
    unittest.main()
