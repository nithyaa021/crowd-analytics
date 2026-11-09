"""Turns raw video frames into tracked people.

This is the "eyes" of the app: YOLO finds people and ByteTrack keeps one ID per person,
so the analytics layer can follow the same person from frame to frame instead of guessing.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from ultralytics import YOLO

from app import config

# Tracker settings file that ships with ultralytics; ByteTrack comes with YOLOv8.
TRACKER_CONFIG = "bytetrack.yaml"


@dataclass
class Person:
    """One detected person in one frame, in pixel coordinates of the resized frame."""

    # Stable number the tracker gives this person across frames (1, 2, 3, ...).
    track_id: int
    # Bounding box as (x1, y1, x2, y2): top-left and bottom-right corners.
    box: tuple[int, int, int, int]
    # How sure YOLO is that this box is a person, between 0 and 1.
    conf: float
    # Bottom-centre of the box, treated as the point where the person touches the floor.
    foot: tuple[int, int]


def foot_point(box: tuple[int, int, int, int]) -> tuple[int, int]:
    """Returns the bottom-centre of a box, the point we treat as the person's feet.

    Why: a box's centre floats around the chest, but feet sit on the floor, and floor
    positions are what zone polygons are drawn around.

    Example: box (100, 50, 140, 200) gives ((100 + 140) // 2, 200) = (120, 200).
    """
    x1, _y1, x2, y2 = box
    # Integer division keeps pixel coordinates whole numbers, which JSON and drawing prefer.
    return (x1 + x2) // 2, y2


def resize_frame(frame: np.ndarray, width: int) -> np.ndarray:
    """Shrinks or grows a frame to a fixed width while keeping its aspect ratio.

    Why: a fixed width makes detection speed, drawing coordinates and the browser stream
    predictable, and aspect ratio stops people from looking stretched.

    Example: a 1280x720 frame at width 640 becomes 640x360 (720 * 640 / 1280 = 360).
    """
    if width < 1:
        raise ValueError("width must be at least 1 pixel")
    height, old_width = frame.shape[:2]
    if old_width == width:
        return frame
    # Same ratio on both sides: new_height / width = height / old_width.
    new_height = round(height * width / old_width)
    # INTER_AREA looks cleaner when shrinking; INTER_LINEAR avoids blur when enlarging.
    interpolation = cv2.INTER_AREA if width < old_width else cv2.INTER_LINEAR
    return cv2.resize(frame, (width, new_height), interpolation=interpolation)


class Detector:
    """Wraps YOLOv8 plus ByteTrack so callers ask for "people", not for tensors."""

    def __init__(self) -> None:
        """Loads the model weights once; loading them for every frame would be far too slow."""
        self.model = YOLO(config.MODEL_PATH)

    def track(self, frame: np.ndarray) -> list[Person]:
        """Finds people in one BGR frame and returns them with stable tracking IDs."""
        results = self.model.track(
            frame,
            persist=True,  # keep tracker state between calls, so IDs stay the same
            tracker=TRACKER_CONFIG,
            classes=[config.PERSON_CLASS_ID],  # ignore bags, cars and other classes
            conf=config.CONF,
            imgsz=config.IMGSZ,
            verbose=False,  # keep the console free for our own summary
        )
        boxes = results[0].boxes
        # Without IDs the tracker did not produce tracks, so there is nothing to return.
        if boxes.id is None:
            return []
        # YOLO returns three parallel arrays: corners, IDs and confidences, one row per person.
        return [
            self._to_person(box, track_id, conf)
            for box, track_id, conf in zip(boxes.xyxy, boxes.id, boxes.conf)
        ]

    @staticmethod
    def _to_person(box: object, track_id: object, conf: object) -> Person:
        """Converts one YOLO tensor row into a plain Person with integer pixels."""
        # tolist() turns a small tensor into normal Python numbers we can round and store.
        x1, y1, x2, y2 = (int(value) for value in box.tolist())
        box_ints = (x1, y1, x2, y2)
        return Person(
            track_id=int(track_id),
            box=box_ints,
            conf=float(conf),  # float() makes the confidence JSON-friendly
            foot=foot_point(box_ints),
        )

    def reset(self) -> None:
        """Restarts tracking IDs at 1, which is needed when we switch to another video."""
        predictor = self.model.predictor
        if predictor is None:
            return
        # Each tracker slot keeps its own counters, so reset every slot that exists.
        for tracker in getattr(predictor, "trackers", []):
            tracker.reset()
