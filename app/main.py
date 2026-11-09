"""The web layer: it serves the dashboard, streams video and answers the JSON API.

Why this file is thin: all the thinking already lives in engine.py (the video loop), db.py (the
history) and zones.py (the geometry). This module's only job is to translate HTTP requests into
calls on those modules and to serialise the answers. Keeping it thin means a web bug is a web
bug, never a detection bug.

Why the engine is a module-level singleton started in lifespan: the model must be loaded once,
not once per request, and a background thread must outlive individual requests but die with the
application. FastAPI's lifespan is exactly that scope.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Iterator

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import config, db
from app.engine import Engine, SharedState, list_clips
from app.zones import load_zones

# The one engine instance for the whole process.
state = SharedState()
engine = Engine(state)

# The MJPEG boundary string. Why a fixed long string: it must never appear inside a JPEG body,
# and a string this unusual effectively cannot.
BOUNDARY = "frame"

# Default and maximum page sizes for the alert feed, so a client cannot ask for everything.
DEFAULT_ALERT_LIMIT = 50
MAX_ALERT_LIMIT = 500

# Default and maximum window for the history chart, in minutes.
DEFAULT_HISTORY_MINUTES = 10
MAX_HISTORY_MINUTES = 24 * 60


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Creates the tables, starts the video thread, and stops cleanly on shutdown.

    Why tables first: the engine writes an alert row within the first few seconds of the crowded
    clip, and that would fail on a fresh machine if the tables did not exist yet.

    Why joining the thread on shutdown: a daemon thread dies with the process anyway, but joining
    gives it a moment to release the video file handle, which keeps Windows from leaving a locked
    file behind after a restart.
    """
    db.init_db()
    engine.start()
    try:
        yield
    finally:
        # daemon=True means the process can always exit; this is a courtesy, not a requirement.
        engine.join(timeout=2.0)


app = FastAPI(title="Crowd Density and Bottleneck Analytics", lifespan=lifespan)

# The dashboard files and the evidence photos are plain files on disk, so StaticFiles serves them
# faster and more correctly (range requests, caching, MIME types) than any hand-written route.
config.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
app.mount(config.EVIDENCE_URL_PREFIX, StaticFiles(directory=config.EVIDENCE_DIR), name="evidence")


@app.get("/")
def index() -> FileResponse:
    """Serves the dashboard page.

    Why FileResponse and not a mounted root: mounting StaticFiles at "/" would swallow every
    other route, including /api. One explicit route for one file keeps the API reachable.

    Example: GET / returns static/index.html with Content-Type text/html.
    """
    return FileResponse(config.BASE_DIR / "static" / "index.html", media_type="text/html")


@app.get("/video")
def video(request: Request, boxes: int = 1, zones: int = 1, heat: int = 0) -> StreamingResponse:
    """Streams the live annotated video as multipart/x-mixed-replace (MJPEG).

    Why this content type: a browser displays a multipart stream inside a plain <img> tag and
    keeps replacing the picture, which gives video with no JavaScript and no WebSocket.

    Why a normal (sync) generator: each frame is a small blocking CPU job (drawing plus JPEG
    encoding). Starlette runs a sync generator in its threadpool, so it does not block the event
    loop that serves /ws and the API. An async generator would block that loop instead.

    Why the sleep: encoding is cheap, but there is no point sending faster than MJPEG_MAX_FPS.
    Without the cap the stream would push the CPU to 100% for no visible gain.

    Why the finally block: when the browser closes the tab, Starlette closes the generator, the
    finally runs, and the loop stops. That is how a disconnecting client frees its CPU share.

    Example: GET /video?boxes=1&zones=1&heat=1 sends frames at up to 15 per second.
    """

    def frames() -> Iterator[bytes]:
        """Produces one MJPEG part per iteration until the client goes away.

        Why check request.client: Starlette closes the generator on disconnect, but an explicit
        check stops one more frame from being rendered for nobody.

        Example: one yielded part is
        --frame\\r\\nContent-Type: image/jpeg\\r\\nContent-Length: 41233\\r\\n\\r\\n<bytes>\\r\\n
        """
        delay = 1.0 / max(config.MJPEG_MAX_FPS, 1)
        try:
            while request.client is not None:
                jpeg = engine.render(boxes=bool(boxes), zones_on=bool(zones), heat=bool(heat))
                yield (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                       f"Content-Length: {len(jpeg)}\r\n\r\n").encode("ascii") + jpeg + b"\r\n"
                # Blocking sleep on purpose: this generator already runs in a worker thread.
                time.sleep(delay)
        finally:
            # Reached when the browser disconnects or the server shuts down.
            return

    return StreamingResponse(
        frames(),
        media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Pushes the newest snapshot to one browser every WS_INTERVAL seconds.

    Why a loop with a sleep instead of sending only on change: the dashboard also needs to know
    that nothing changed (so it can show "last update 0.5 s ago"). A steady beat is simpler than
    diffing, and the payload is about 500 bytes.

    Why catch WebSocketDisconnect: a closed tab raises it, and that is normal, not an error.
    Without the catch, every tab close would print a traceback in the server log.

    Example: 10 clients each receive 2 snapshots per second at WS_INTERVAL 0.5.
    """
    await websocket.accept()
    try:
        while True:
            _, _, snapshot = state.get()
            # send_json handles the encoding, so the snapshot must already be plain Python types.
            await websocket.send_json(snapshot)
            await asyncio.sleep(config.WS_INTERVAL)
    except WebSocketDisconnect:
        return


@app.get("/api/zones")
def api_zones(source: str | None = None) -> list[dict]:
    """Returns the configured zones for one clip, or for the clip currently playing.

    Why default to the playing clip: the dashboard asks "what zones are on screen right now?"
    and should not have to know the source name first.

    Example: [{"name": "Main Zone", "capacity": 4, "polygon": [[284, 232], ...]}]
    """
    name = source or engine.current_source()
    zones = load_zones(config.ZONES_FILE, name)
    return [
        {"name": zone.name, "capacity": int(zone.capacity), "polygon": zone.points()}
        for zone in zones
    ]


@app.get("/api/alerts")
def api_alerts(limit: int = Query(DEFAULT_ALERT_LIMIT, ge=1, le=MAX_ALERT_LIMIT)) -> list[dict]:
    """Returns the newest alerts, newest first, for the alert table in the dashboard.

    Why the Query bounds: `ge=1` stops a zero or negative limit, and `le=500` stops a client from
    asking for the entire history in one request. FastAPI turns a violation into a 422, which is
    the correct answer for a bad parameter.

    Example: GET /api/alerts?limit=2 returns at most 2 rows, the highest ids first.
    """
    return db.list_alerts(limit=limit)


@app.get("/api/history")
def api_history(
    minutes: int = Query(DEFAULT_HISTORY_MINUTES, ge=1, le=MAX_HISTORY_MINUTES),
) -> list[dict]:
    """Returns head-count samples from the last N minutes, oldest first, for the line chart.

    Why oldest first: a chart plots left to right in time order, so the data arrives ready to
    draw and the browser does not have to sort it.

    Example: GET /api/history?minutes=10 returns rows with ts, zone and count.
    """
    return db.headcount_since(minutes=minutes)


@app.get("/api/sources")
def api_sources() -> list[str]:
    """Lists the clip file names the engine will accept.

    Why expose this: the dashboard's source picker must offer exactly the names that
    POST /api/source will accept, so the list comes from the same allow-list function.

    Example: ["crowded.mp4", "mid.mp4", "normal.mp4"].
    """
    return list_clips()


@app.post("/api/source")
async def api_set_source(request: Request) -> dict:
    """Switches the engine to another clip.

    Why read the JSON by hand: the body is a single optional field, and a hand-written check lets
    us return a clear 400 instead of FastAPI's 422 for a name we simply do not have.

    Why 400 and not 404: the request is malformed (it names something that is not a valid
    source), not a missing page. 400 tells the client "fix your body".

    Example: {"name": "mid.mp4"} -> 200 {"ok": true, "source": "mid.mp4"}.
             {"name": "../../zones.json"} -> 400 {"detail": "Unknown source: ..."}.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Body must be JSON") from error

    name = payload.get("name") if isinstance(payload, dict) else None
    if not isinstance(name, str) or name not in list_clips():
        raise HTTPException(status_code=400, detail=f"Unknown source: {name!r}")

    engine.set_source(name)
    return {"ok": True, "source": name}
