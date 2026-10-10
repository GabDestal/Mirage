"""SQLite event log: one stream for everything (CONTRACTS.md §4, Event).

Each row is hash-chained to the previous one, so the log is tamper-evident.
"""

import hashlib
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from contracts.models import Event

DB_PATH = Path(os.getenv("MIRAGE_DB", "data/mirage.db"))
listeners = []  # callables(Event): the CLI printer now, the SSE stream later

_lock = threading.Lock()
_conn = None


def _db():
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, ts TEXT, run_id TEXT,"
            " incident_id TEXT, env TEXT, type TEXT, body TEXT, prev_hash TEXT, hash TEXT)"
        )
    return _conn


def reset():
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None
        for suffix in ("", "-wal", "-shm"):
            Path(f"{DB_PATH}{suffix}").unlink(missing_ok=True)


def emit(type, payload=None, *, env="prod", run_id=None, incident_id=None) -> Event:
    with _lock:
        db = _db()
        last = db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev_hash = (last[0] + 1, last[1]) if last else (1, "")
        event = Event(seq=seq, ts=datetime.now(UTC), run_id=run_id, incident_id=incident_id,
                      env=env, type=type, payload=payload or {})
        body = event.model_dump_json()
        digest = hashlib.sha256((prev_hash + body).encode()).hexdigest()
        db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                   (seq, event.ts.isoformat(), run_id, incident_id, env, type, body,
                    prev_hash, digest))
        db.commit()
    for listener in listeners:
        listener(event)
    return event


def read(after=0) -> list[Event]:
    with _lock:
        rows = _db().execute("SELECT body FROM events WHERE seq > ? ORDER BY seq", (after,))
        return [Event.model_validate_json(body) for (body,) in rows]
