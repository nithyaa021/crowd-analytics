"""Captures docs/dashboard.png from the running app, using a headless Chrome.

Why this exists: the README and the handbook both embed a screenshot, and a stale screenshot of an
old design is worse than none - a panel member comparing the picture to the live page would find
them different. Running this script is the one step needed to refresh both.

Why headless Chrome and not a screenshot tool: the whole thing must run on Windows with no extra
Python package, and every Windows machine that has Chrome has this flag set already. The browser
tool inside an editor is tied to a visible window, which is exactly what a script cannot rely on.

Usage (the app must already be running on port 8000):

    python scripts/make_screenshot.py

It waits 30 s of virtual time so the engine has reached the crowded part of the clip and an alert
is on screen; a screenshot of an empty scene proves nothing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "dashboard.png"

# Where Chrome or Edge usually live on Windows. Why both: Edge ships with Windows, Chrome may not.
CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

# The window size. Why 1440 wide: that is a laptop screen at 100 percent scaling, where the
# 12-column layout is the one a viewer will actually see. The height stops just below the footer.
WINDOW = "1440,1060"

# Virtual time, in milliseconds. Why 30 s: the crowded clip reaches its peak at about 31 s of video,
# and processing runs slower than real time, so this leaves the page in an alert state.
BUDGET_MS = "30000"


def find_browser() -> Path:
    """Returns the first installed Chrome or Edge, or exits with a clear message."""
    for candidate in CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit("No Chrome or Edge found. Install one, or take the screenshot by hand.")


def capture(browser: Path) -> None:
    """Runs the browser once in headless mode and writes the screenshot over docs/dashboard.png."""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={WINDOW}",
        f"--virtual-time-budget={BUDGET_MS}",
        f"--screenshot={OUT}",
        # A cache-busting query, because the browser will otherwise reuse a cached stylesheet.
        f"http://127.0.0.1:8000/?shot={sys.argv[1] if len(sys.argv) > 1 else 'docs'}",
    ]
    print("running:", " ".join(command))
    # The browser prints its own noise to stderr, which is not a failure; the file is the proof.
    subprocess.run(command, check=False, capture_output=True)
    if not OUT.exists():
        raise SystemExit(f"the browser wrote no file at {OUT}")


def main() -> None:
    """Captures the screenshot and reports its size, so a blank or truncated image is obvious."""
    capture(find_browser())
    try:
        from PIL import Image
    except ImportError:
        print(f"wrote {OUT}")
        return
    with Image.open(OUT) as img:
        print(f"wrote {OUT}  {img.size[0]}x{img.size[1]}  "
              f"({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
