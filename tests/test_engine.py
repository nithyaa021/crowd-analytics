"""Tests for SharedState, the one hand-off point between the engine thread and the web threads.

Why this file is worth its own tests: SharedState is where a threading bug would appear as a
torn frame, a snapshot from a different moment than the picture, or a list changing size while a
reader iterates it. Those bugs are rare, intermittent and very hard to debug on stage, so the
"share copies" contract is pinned down here instead.

Run them with: .venv\\Scripts\\python.exe -m unittest -v
"""

import sys
import threading
import unittest
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.engine import SharedState, list_clips


class SharedStateTests(unittest.TestCase):
    """Checks the copying and locking behaviour the whole backend relies on."""

    def test_empty_state_is_safe_to_read(self) -> None:
        """Before the first frame exists, get() must return a valid blank snapshot, not raise.

        Why: the dashboard connects the instant the server starts, and the engine may still be
        loading YOLO. Sending an empty dict would break the snapshot contract, so a zeroed
        snapshot with every required key is returned instead.
        """
        state = SharedState()
        frame, people, snapshot = state.get()
        self.assertIsNone(frame)
        self.assertEqual(people, [])
        self.assertEqual(snapshot["ts"], 0.0)
        self.assertEqual(snapshot["total_people"], 0)
        self.assertEqual(snapshot["zones"], [])
        self.assertIsNone(snapshot["new_alert"])
        self.assertIsNone(state.get_heat())

    def test_frame_is_copied_on_the_way_in(self) -> None:
        """The engine must be able to reuse its buffer after publishing without changing ours.

        Why: the engine decodes into one frame array. If SharedState kept a reference, the next
        decode would overwrite the image the JPEG encoder was halfway through reading.
        """
        state = SharedState()
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        state.set(frame=frame)
        # Simulate the engine reusing its buffer for the next frame.
        frame[:] = 255
        stored, _, _ = state.get()
        self.assertEqual(int(stored.max()), 0)

    def test_frame_is_copied_on_the_way_out(self) -> None:
        """A reader must not be able to modify the state by drawing on the frame it received.

        Why: engine.render() draws boxes on the frame it gets. Without a copy on the way out, those
        boxes would be painted into the stored frame and would accumulate forever.
        """
        state = SharedState()
        state.set(frame=np.zeros((10, 10, 3), dtype=np.uint8))
        frame, _, _ = state.get()
        frame[:] = 255
        stored, _, _ = state.get()
        self.assertEqual(int(stored.max()), 0)

    def test_snapshot_is_deep_copied(self) -> None:
        """Nested lists in the snapshot must not be shared with the caller.

        Why: the snapshot contains a list of zone dicts. A shallow copy would share those dicts,
        so a reader editing one would corrupt the state for everybody.
        """
        state = SharedState()
        snapshot = {"ts": 1.0, "zones": [{"name": "Main Zone", "count": 5}]}
        state.set(snapshot=snapshot)
        # Mutating what we passed in must not affect what is stored.
        snapshot["zones"][0]["count"] = 99
        _, _, stored = state.get()
        self.assertEqual(stored["zones"][0]["count"], 5)

    def test_partial_set_leaves_other_parts_alone(self) -> None:
        """Updating only the snapshot must keep the frame and people that were already there.

        Why: the engine calls set() with all four arguments every frame, but a test or a future
        caller may update one piece, and the others must not silently become empty.
        """
        state = SharedState()
        state.set(frame=np.full((4, 4, 3), 7, dtype=np.uint8), snapshot={"ts": 1.0})
        state.set(snapshot={"ts": 2.0})
        frame, _, snapshot = state.get()
        self.assertEqual(int(frame[0, 0, 0]), 7)
        self.assertEqual(snapshot["ts"], 2.0)

    def test_frame_and_snapshot_always_match(self) -> None:
        """A reader must never see a frame from one moment and a snapshot from another.

        Why this is the real contract: the boxes drawn on the video and the numbers beside it must
        describe the same instant. The writer below updates both together, and the reader checks
        that the frame's brightness equals the snapshot's ts - which only holds if the pair is
        read under one lock.
        """
        state = SharedState()
        stop = threading.Event()
        mismatches: list[tuple[int, int]] = []

        def writer() -> None:
            """Publishes 200 frames, each whose brightness matches its own timestamp."""
            for index in range(200):
                frame = np.full((8, 8, 3), index % 256, dtype=np.uint8)
                state.set(frame=frame, snapshot={"ts": index})
            stop.set()

        def reader() -> None:
            """Reads until the writer finishes, recording any frame/ts disagreement."""
            while not stop.is_set():
                frame, _, snapshot = state.get()
                if frame is None or not snapshot:
                    continue
                if int(frame[0, 0, 0]) != snapshot["ts"]:
                    mismatches.append((int(frame[0, 0, 0]), snapshot["ts"]))

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(mismatches, [])


class ListClipsTests(unittest.TestCase):
    """Checks the allow-list that protects set_source from a path coming from the browser."""

    def test_lists_only_mp4_files_from_the_video_folder(self) -> None:
        """Every entry must be a bare file name ending in .mp4, never a path.

        Why: set_source accepts a value only if it is in this list, so if this list could contain
        a path like "../../zones.json", the security boundary would be gone.
        """
        clips = list_clips()
        self.assertTrue(clips)
        for clip in clips:
            self.assertTrue(clip.endswith(".mp4"), clip)
            self.assertNotIn("/", clip)
            self.assertNotIn("\\", clip)


if __name__ == "__main__":
    unittest.main()
