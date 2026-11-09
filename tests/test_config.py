"""Tests for the settings file, so a typo in config.py fails fast instead of at demo time.

Run them with: .venv\\Scripts\\python.exe -m unittest discover -s tests -t . -v
"""

import json
import sys
import unittest
from pathlib import Path

# Make "from app import config" work even if this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config


class ConfigTests(unittest.TestCase):
    """Checks the few config values that other steps will depend on."""

    def test_conf_is_the_agreed_value(self) -> None:
        """A confidence of 0.35 keeps weak guesses out; a typo like 35 would break detection."""
        self.assertAlmostEqual(config.CONF, 0.35)

    def test_paths_are_absolute_and_named(self) -> None:
        """Absolute paths mean the app finds its files no matter which folder it is started from."""
        self.assertTrue(config.BASE_DIR.is_absolute())
        self.assertEqual(config.ZONES_FILE.name, "zones.json")
        self.assertEqual(config.DB_PATH.name, "crowd.db")
        self.assertEqual(config.DB_PATH.parent.name, "results")

    def test_zones_file_is_valid_json_with_the_expected_shape(self) -> None:
        """zones.json must parse and map each clip name to a list of zones.

        Step P0 shipped this file as {}, and P3 fills it in. So this test no longer demands an
        empty file; it checks the contract everyone relies on: a JSON object whose keys are
        clip file names and whose values are lists of zones with name, capacity and polygon.
        """
        with open(config.ZONES_FILE, encoding="utf-8") as zones_file:
            data = json.load(zones_file)
        self.assertIsInstance(data, dict)
        for clip_name, zones in data.items():
            self.assertTrue(clip_name.endswith(".mp4"), clip_name)
            self.assertIsInstance(zones, list)
            for zone in zones:
                self.assertEqual({"name", "capacity", "polygon"}, set(zone))
                # A polygon needs at least a triangle, and each point needs an x and a y.
                self.assertGreaterEqual(len(zone["polygon"]), 3)
                for point in zone["polygon"]:
                    self.assertEqual(len(point), 2)


if __name__ == "__main__":
    unittest.main()
