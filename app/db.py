"""Owns the SQLite database: the alert history and the head-count history.

Why a separate module: two different things need the same tables - the live engine writes to
them while the video runs, and the API reads from them for the dashboard. Keeping every SQL
statement in one file means there is exactly one place to check when a number looks wrong.

Each function opens its own short-lived connection and closes it again. Why: SQLite objects
cannot be shared between threads, and the engine runs in a background thread while FastAPI
answers requests in others. A per-call connection sidesteps that entirely, and because every
call is a single small query, the cost is negligible (microseconds on a local file).

Every value that comes from outside is passed as a `?` parameter, never formatted into the SQL
string. Why: a zone name or a source file name is user-controlled, and string formatting would
open the door to SQL injection - and also break on any name containing a quote.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app import config

# The two tables, exactly as the project spec defines them.
# Why "IF NOT EXISTS": init_db() runs on every server start, and a second run must be harmless.
SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    video_ts REAL NOT NULL,
    ended_at TEXT,
    peak_count INTEGER NOT NULL,
    capacity INTEGER NOT NULL,
    keyframe TEXT
);

CREATE TABLE IF NOT EXISTS headcount (
    ts TEXT NOT NULL,
    zone TEXT NOT NULL,
    count INTEGER NOT NULL
);
"""

# Default row cap for list_alerts, so a caller cannot accidentally ask for a million rows.
DEFAULT_ALERT_LIMIT = 50


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Opens one connection, hands it to the caller, then commits and closes it.

    Why a context manager: it guarantees the file handle is closed even if the query raises,
    which on Windows matters - a leaked handle keeps the .db file locked and the next write
    fails with "database is locked".

    Why row_factory: it lets callers read a row as a dict, so the API can return it as JSON
    without remembering column positions.

    Example: with connect() as connection: connection.execute(...)
    """
    path = Path(db_path) if db_path is not None else config.DB_PATH
    # The folder may not exist yet on a fresh clone, and sqlite3 will not create it.
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10.0)
    # Reading a row by column name is far more readable than by index number.
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_path: Path | None = None) -> None:
    """Creates the two tables if they are missing, and does nothing if they already exist.

    Why: the server must be startable on a fresh machine with no database file at all, and
    must not wipe the history when it is restarted.

    Example: first run creates results/crowd.db with 0 rows; second run leaves it untouched.
    """
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)


def utc_now_iso() -> str:
    """Returns the current wall-clock time as an ISO-8601 string in UTC.

    Why the wall clock here and not video time: `started_at` answers "when did this happen in
    real life?" for the alert history, while `video_ts` answers "where in the clip?". They are
    different questions and both are stored.

    Why UTC: a single unambiguous timeline, so sorting alerts as text still sorts them by time.

    Example: 2026-11-09T14:03:21.512345+00:00
    """
    return datetime.now(timezone.utc).isoformat()


def insert_alert(zone: str, source: str, video_ts: float, count: int, capacity: int,
                 keyframe: str | None, started_at: str | None = None,
                 db_path: Path | None = None) -> int:
    """Inserts one new alert row and returns its auto-generated id.

    Why return the id: the engine needs it immediately to name the evidence photo
    `alert_<id>.jpg` and to report it to the browser, and only the database can allocate it.

    Example: the first alert of the session returns 1; the photo becomes evidence/alert_1.jpg.
    """
    with connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO alerts (zone, source, started_at, video_ts, ended_at, peak_count,"
            " capacity, keyframe) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
            (zone, source, started_at or utc_now_iso(), float(video_ts), int(count),
             int(capacity), keyframe),
        )
        return int(cursor.lastrowid)


def end_alert(alert_id: int, ended_at: str | None = None,
              db_path: Path | None = None) -> None:
    """Stamps the end time on one alert, marking the episode as finished.

    Why not delete the row: the whole point of the history is that past overcrowding stays
    visible after the crowd is gone.

    Example: alert 1 ended at 2026-11-09T14:04:02+00:00 keeps peak_count 9 for the chart.
    """
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE alerts SET ended_at = ? WHERE id = ?",
            (ended_at or utc_now_iso(), int(alert_id)),
        )


def update_peak(alert_id: int, count: int, db_path: Path | None = None) -> None:
    """Raises the stored peak of an active alert, but never lowers it.

    Why `MAX(peak_count, ?)` in SQL instead of reading, comparing in Python and writing back:
    one statement cannot be interrupted between the read and the write, so a concurrent writer
    can never lower a peak that a previous writer already raised.

    Example: peak 7 then a count of 5 leaves 7; a count of 9 becomes 9.
    """
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE alerts SET peak_count = MAX(peak_count, ?) WHERE id = ?",
            (int(count), int(alert_id)),
        )


def set_keyframe(alert_id: int, keyframe: str, db_path: Path | None = None) -> None:
    """Attaches the evidence photo's URL to an alert row.

    Why a separate call: the photo's file name contains the alert id, so the row must exist
    before the picture can be named. Inserting first and updating the path second is the
    simplest way to get that ordering right.

    Example: alert 3 plus evidence/alert_3.jpg stores keyframe "/evidence/alert_3.jpg".
    """
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE alerts SET keyframe = ? WHERE id = ?",
            (keyframe, int(alert_id)),
        )


def list_alerts(limit: int = DEFAULT_ALERT_LIMIT,
                db_path: Path | None = None) -> list[dict]:
    """Returns the newest alerts first, as plain dicts the API can serialise directly.

    Why newest first: the dashboard shows a feed, and the most recent alert is the one an
    operator cares about. Why a limit: an unbounded query would grow with the history.

    Example: limit 2 on alerts 1, 2 and 3 returns 3 then 2.
    """
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, zone, source, started_at, video_ts, ended_at, peak_count, capacity,"
            " keyframe FROM alerts ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def add_headcount(ts: str, zone: str, count: int, db_path: Path | None = None) -> None:
    """Appends one head-count sample for one zone.

    Why store the timestamp as a string: ISO-8601 in UTC sorts alphabetically in the same
    order it sorts in time, so `WHERE ts >= ?` and ORDER BY both work without parsing dates.

    Example: ts "2026-11-09T14:03:21+00:00", zone "Main Zone", count 7.
    """
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO headcount (ts, zone, count) VALUES (?, ?, ?)",
            (ts, zone, int(count)),
        )


def headcount_since(minutes: int, db_path: Path | None = None) -> list[dict]:
    """Returns every head-count sample from the last `minutes` minutes, oldest first.

    Why oldest first here (unlike alerts): a line chart plots time left to right, so the API
    hands the points over already in drawing order.

    Why the cut-off is computed as a UTC string: it can then be compared directly with the
    stored strings, so no date parsing happens per row.

    Example: minutes 10 at 14:10 keeps samples from 14:00 onwards and drops older ones.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - int(minutes) * 60
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT ts, zone, count FROM headcount WHERE ts >= ? ORDER BY ts ASC",
            (cutoff_iso,),
        ).fetchall()
    return [dict(row) for row in rows]
