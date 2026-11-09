"""Starts the real server and checks every P5 endpoint end to end.

Why this exists: unit tests prove functions work in isolation, but P5 is a wiring step - the
failure mode here is "the pieces are fine but the app does not start". Only a real uvicorn
process can catch that: the lifespan, the background engine thread, the static mounts, the MJPEG
stream and the WebSocket handshake are all things a TestClient would not exercise the same way.

Why it waits for the engine rather than sleeping a fixed time: loading YOLO takes a second or two
on CPU, and a hard-coded sleep is either flaky or slow. The script polls /api/zones and /ws until
the engine has published a real snapshot, with a clear timeout if it never does.

Run: .venv\\Scripts\\python.exe scripts\\smoke_test.py
"""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Teach Python where the project root is, because this file sits one folder deeper than app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config

# A port unlikely to clash with anything else on a demo laptop.
HOST = "127.0.0.1"
PORT = 8011
BASE_URL = f"http://{HOST}:{PORT}"

# How long the server may take to answer its first request, and how long the engine may take to
# publish its first snapshot (YOLO loading plus one frame on CPU).
SERVER_TIMEOUT = 60.0
SNAPSHOT_TIMEOUT = 120.0
# How many bytes of the MJPEG stream are enough to prove it contains a full JPEG part.
STREAM_BYTES = 4096

# Every key the SNAPSHOT contract requires, in one place so a missing key is named in the error.
REQUIRED_SNAPSHOT_KEYS = {
    "ts", "source", "fps", "total_people", "peak_people", "zones",
    "alerts_active", "new_alert",
}
REQUIRED_ZONE_KEYS = {
    "name", "count", "capacity", "fill", "status", "over_for", "avg_dwell", "max_dwell",
}

# Collected results as (name, ok, detail) so the final report can list every check at once.
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    """Stores one check's outcome and prints it immediately, so a failure is visible in order.

    Why print as we go: if a later check hangs, the earlier passes are already on screen and the
    report shows exactly where it stopped.
    """
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" - {detail}" if detail else ""))


def port_is_free(port: int) -> bool:
    """Returns True when nothing is listening on the port.

    Why: a leftover server from a previous run would make this script test the wrong process and
    report success against stale code. Failing fast with a clear message is better.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) != 0


def wait_for_server(client: httpx.Client) -> bool:
    """Polls GET / until the server answers, or the timeout expires.

    Why: uvicorn has to import ultralytics and start the engine thread before the first response.
    Polling turns that startup time into a pass instead of a race.
    """
    deadline = time.time() + SERVER_TIMEOUT
    while time.time() < deadline:
        try:
            if client.get("/", timeout=2.0).status_code == 200:
                return True
        except httpx.HTTPError:
            # Not listening yet; the expected state for the first second or two.
            pass
        time.sleep(0.5)
    return False


def check_index(client: httpx.Client) -> None:
    """GET / must return 200 and the dashboard HTML, not a directory listing or a 404."""
    response = client.get("/")
    ok = response.status_code == 200 and "img" in response.text.lower()
    record("GET / returns 200 with the dashboard page", ok, f"status {response.status_code}")


def check_docs(client: httpx.Client) -> None:
    """GET /docs must return 200; it proves FastAPI itself mounted correctly."""
    response = client.get("/docs")
    record("GET /docs returns 200", response.status_code == 200,
           f"status {response.status_code}")


def check_zones(client: httpx.Client) -> None:
    """GET /api/zones must be a non-empty list of zones with the expected keys."""
    response = client.get("/api/zones")
    payload = response.json() if response.status_code == 200 else None
    ok = (
        isinstance(payload, list)
        and len(payload) > 0
        and all({"name", "capacity", "polygon"} <= set(zone) for zone in payload)
    )
    detail = f"{len(payload)} zone(s)" if isinstance(payload, list) else "not a list"
    record("GET /api/zones is a list of zones", bool(ok), detail)


def check_sources(client: httpx.Client) -> None:
    """GET /api/sources must list exactly the three demo clips."""
    payload = client.get("/api/sources").json()
    expected = {"normal.mp4", "mid.mp4", "crowded.mp4"}
    ok = isinstance(payload, list) and set(payload) == expected
    record("GET /api/sources lists the three clips", bool(ok), ", ".join(sorted(payload)))


def check_source_switch_rejects_bad_name(client: httpx.Client) -> None:
    """POST /api/source with a path must be refused with 400, not accepted or crashed on.

    Why this check matters: it is the security boundary. A server that accepted
    "../../zones.json" would let a browser read any file the process can open.
    """
    response = client.post("/api/source", json={"name": "../../zones.json"})
    record("POST /api/source rejects a path with 400", response.status_code == 400,
           f"status {response.status_code}")


def check_source_switch(client: httpx.Client) -> None:
    """POST /api/source with a real clip must return 200 and report that clip back."""
    response = client.post("/api/source", json={"name": "normal.mp4"})
    ok = response.status_code == 200 and response.json().get("source") == "normal.mp4"
    record("POST /api/source accepts a real clip", ok, f"status {response.status_code}")


def check_websocket_snapshot() -> dict[str, Any] | None:
    """Reads one snapshot from /ws and checks every contract key.

    Why use the websockets library and not httpx: WebSocket is a different protocol, and only a
    real client can prove the handshake and the push loop work.

    Why loop until a non-empty snapshot: the very first message can arrive before the engine has
    published anything, which is a timing artefact rather than a bug.
    """
    import asyncio

    import websockets

    async def read_one() -> dict[str, Any] | None:
        """Connects, then returns the first snapshot that has a source and a timestamp."""
        url = f"ws://{HOST}:{PORT}/ws"
        deadline = time.time() + SNAPSHOT_TIMEOUT
        async with websockets.connect(url, open_timeout=30) as socket_:
            while time.time() < deadline:
                message = await asyncio.wait_for(socket_.recv(), timeout=SNAPSHOT_TIMEOUT)
                snapshot = json.loads(message)
                if snapshot.get("source") and snapshot.get("ts"):
                    return snapshot
        return None

    snapshot = asyncio.run(read_one())
    if snapshot is None:
        record("/ws delivers a snapshot with all contract keys", False, "no snapshot arrived")
        return None

    missing = REQUIRED_SNAPSHOT_KEYS - set(snapshot)
    if missing:
        record("/ws delivers a snapshot with all contract keys", False,
               f"missing {sorted(missing)}")
        return snapshot

    zones = snapshot["zones"]
    if not isinstance(zones, list) or not zones:
        record("/ws delivers a snapshot with all contract keys", False, "zones is empty")
        return snapshot

    missing_zone = REQUIRED_ZONE_KEYS - set(zones[0])
    if missing_zone:
        record("/ws delivers a snapshot with all contract keys", False,
               f"zone missing {sorted(missing_zone)}")
        return snapshot

    record("/ws delivers a snapshot with all contract keys", True,
           f"source {snapshot['source']}, ts {snapshot['ts']:.2f}, "
           f"{snapshot['total_people']} people")
    return snapshot


def check_video_stream(client: httpx.Client) -> None:
    """Reads a few kilobytes of /video and checks for the multipart header and JPEG bytes.

    Why not read the whole stream: it never ends by design. Reading a small slice proves the
    content type, the boundary and the presence of JPEG data, then closes the connection.

    Why stream() rather than get(): get() would try to download an infinite response.
    """
    with client.stream("GET", "/video?boxes=1&zones=1&heat=1", timeout=30.0) as response:
        content_type = response.headers.get("content-type", "")
        collected = b""
        for chunk in response.iter_bytes():
            collected += chunk
            if len(collected) >= STREAM_BYTES:
                break
    # JPEG files start with the bytes FF D8 (SOI marker); finding them proves real image data.
    ok = (
        response.status_code == 200
        and "multipart/x-mixed-replace" in content_type
        and b"\xff\xd8" in collected
        and b"--frame" in collected
    )
    record("GET /video returns an MJPEG part with JPEG data", ok,
           f"{len(collected)} bytes, content-type {content_type.split(';')[0]}")


def check_history(client: httpx.Client) -> None:
    """GET /api/history must be a list. It may be short, but it must not error.

    Why check it: it is the endpoint most likely to break quietly, because it queries a table
    that is empty for the first two video seconds.
    """
    response = client.get("/api/history?minutes=10")
    payload = response.json() if response.status_code == 200 else None
    record("GET /api/history returns a list", isinstance(payload, list) and response.status_code == 200,
           f"{len(payload)} row(s)" if isinstance(payload, list) else "not a list")


def check_alerts(client: httpx.Client) -> None:
    """GET /api/alerts must be a list and must accept the limit parameter."""
    response = client.get("/api/alerts?limit=5")
    payload = response.json() if response.status_code == 200 else None
    ok = isinstance(payload, list) and response.status_code == 200
    record("GET /api/alerts returns a list", ok,
           f"{len(payload)} alert(s)" if isinstance(payload, list) else "not a list")


def start_server() -> subprocess.Popen:
    """Launches uvicorn as a child process and returns it so it can be stopped afterwards.

    Why a child process rather than a thread: the smoke test must prove the exact command in
    start.bat works, including module import order and the lifespan.

    Why the output is left visible: if startup fails, the traceback is the only useful evidence,
    and hiding it would make the test useless.
    """
    return subprocess.Popen(
        [str(config.BASE_DIR / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn",
         "app.main:app", "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
        cwd=str(config.BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_server(server: subprocess.Popen) -> str:
    """Terminates the child process and returns whatever it printed.

    Why terminate then wait: SIGTERM lets uvicorn run its shutdown path, which joins the engine
    thread and releases the video file. Killing outright can leave the .db file locked.
    """
    server.terminate()
    try:
        output, _ = server.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        server.kill()
        output, _ = server.communicate()
    return output or ""


def main() -> int:
    """Runs every check and returns 0 on success, 1 if anything failed.

    Why an exit code: a script that prints failures but exits 0 looks like a pass to any
    automation, including the reader's eye.
    """
    if not port_is_free(PORT):
        print(f"Port {PORT} is already in use. Stop the other server and re-run.")
        return 1

    print(f"Starting uvicorn on {BASE_URL} ...")
    server = start_server()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
            if not wait_for_server(client):
                print("Server did not answer within the timeout.")
                return 1
            print("Server is up. Checking endpoints:")

            check_index(client)
            check_docs(client)
            check_zones(client)
            check_sources(client)
            check_source_switch_rejects_bad_name(client)
            check_source_switch(client)
            check_history(client)
            check_alerts(client)
            check_websocket_snapshot()
            check_video_stream(client)
    finally:
        server_output = stop_server(server)

    failed = [name for name, ok, _ in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} checks passed.")
    if failed:
        print("Failed checks:")
        for name in failed:
            print(f"  - {name}")
        if server_output.strip():
            print("\nServer output:\n" + server_output)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
