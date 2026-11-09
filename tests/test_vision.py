"""Tests for the vision layer, so a silent detection bug fails here instead of at the demo.

Run them with: .venv\\Scripts\\python.exe -m unittest -v
"""

import sys
import unittest
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.vision import Detector, foot_point, resize_frame


class FootPointTests(unittest.TestCase):
    """Checks the one piece of geometry the zones will depend on."""

    def test_foot_point_is_bottom_centre(self) -> None:
        """Box (100,50,140,200) must give (120,200): halfway across, on the bottom edge."""
        self.assertEqual(foot_point((100, 50, 140, 200)), (120, 200))


class ResizeFrameTests(unittest.TestCase):
    """Checks that resizing never stretches people out of shape."""

    def test_resize_keeps_aspect_ratio(self) -> None:
        """A 1280x720 frame at width 640 must become 640x360, not a squashed square."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.assertEqual(resize_frame(frame, 640).shape, (360, 640, 3))

    def test_resize_can_enlarge(self) -> None:
        """A 320x240 frame at width 640 must become 640x480, so growth uses the same maths."""
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertEqual(resize_frame(frame, 640).shape, (480, 640, 3))

    def test_same_width_returns_the_same_frame(self) -> None:
        """If the width already matches we reuse the frame, which saves a pointless copy."""
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        self.assertIs(resize_frame(frame, 200), frame)


class DetectorTests(unittest.TestCase):
    """Checks the detector survives the "nothing here" case."""

    def test_blank_image_has_no_people(self) -> None:
        """A black frame has no person: we must get [] back, not an error or a fake box."""
        detector = Detector()
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertEqual(detector.track(blank), [])


if __name__ == "__main__":
    unittest.main()
