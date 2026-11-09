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

    def test_zones_file_holds_an_empty_json_object(self) -> None:
        """Step P0 ships zones.json as {}, so this test proves the file exists and parses."""
        with open(config.ZONES_FILE, encoding="utf-8") as zones_file:
            self.assertEqual(json.load(zones_file), {})


if __name__ == "__main__":
    unittest.main()
