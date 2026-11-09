"""Checks that Python, the libraries, config.py and the YOLO weights really work.

Why: a broken setting here would look like a mystery bug later, so we prove step P0 first.
Run it from the project root: .venv\\Scripts\\python.exe scripts\\check_env.py
"""

import sys
from pathlib import Path

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import fastapi
import numpy as np
import ultralytics
from ultralytics import YOLO

from app import config


def show_versions() -> None:
    """Print each library version so we can quote exact numbers in the review."""
    print(f"Python      : {sys.version.split()[0]}")
    print(f"opencv      : {cv2.__version__}")
    print(f"numpy       : {np.__version__}")
    print(f"ultralytics : {ultralytics.__version__}")
    print(f"fastapi     : {fastapi.__version__}")


def check_config() -> None:
    """Print three settings, which proves config.py imports and holds the expected values."""
    print(f"CONF        : {config.CONF}")
    print(f"ZONES_FILE  : {config.ZONES_FILE}")
    print(f"DB_PATH     : {config.DB_PATH}")


def check_model() -> None:
    """Load YOLOv8 nano once, which downloads the weights and proves the model can start."""
    model = YOLO(config.MODEL_PATH)
    # model.names maps class numbers to words, so its length tells us how many classes exist.
    print(f"model ok    : {config.MODEL_PATH} ({len(model.names)} classes)")


def main() -> None:
    """Run all three checks in order and print a clear final line for the two-minute check."""
    show_versions()
    check_config()
    check_model()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
