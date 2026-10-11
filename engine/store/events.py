"""SQLite event log: one stream for everything (CONTRACTS.md §4, Event).

Each row is hash-chained to the previous one, so the log is tamper-evident.
"""

import hashlib
import os
import re
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from contracts.models import Event

DB_PATH = Path(os.getenv("MIRAGE_DB", "data/mirage.db"))
listeners = []  # callables(Event): the CLI printer now, the SSE stream later

_lock = threading.Lock()
_conn = None
_identity = None
_epoch = None


def _db():
    global _conn, _identity, _epoch
    try:
        stat = DB_PATH.stat()
        identity = (str(DB_PATH.resolve()), stat.st_dev, stat.st_ino)
    except FileNotFoundError:
        identity = None
    if _conn is not None and identity != _identity:
        _conn.close()  # an external reset replaced the file behind this connection
        _conn = None
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # autocommit mode: emit() opens its own BEGIN IMMEDIATE; timeout waits for other writers
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None,
                                timeout=10)
        # Switching a fresh file to WAL needs an exclusive lock and skips the busy timeout:
        # two processes opening a new log at once (API + agents) would crash. Retry briefly.
        for attempt in range(50):
            try:
                _conn.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError:
                if attempt == 49:
                    raise
                time.sleep(0.1)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, ts TEXT, run_id TEXT,"
            " incident_id TEXT, env TEXT, type TEXT, body TEXT, prev_hash TEXT, hash TEXT)"
        )
        stat = DB_PATH.stat()
        _identity = (str(DB_PATH.resolve()), stat.st_dev, stat.st_ino)
        _epoch = uuid4().hex
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
        # The write lock is taken before reading the last seq, so two processes (API, CLI,
        # agents) can never give two events the same seq.
        db.execute("BEGIN IMMEDIATE")
        try:
            last = db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev_hash = (last[0] + 1, last[1]) if last else (1, "")
            event = Event(seq=seq, ts=datetime.now(UTC), run_id=run_id, incident_id=incident_id,
                          env=env, type=type, payload=payload or {})
            body = event.model_dump_json()
            digest = hashlib.sha256((prev_hash + body).encode()).hexdigest()
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                       (seq, event.ts.isoformat(), run_id, incident_id, env, type, body,
                        prev_hash, digest))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    for listener in listeners:
        listener(event)
    return event


def read(after=0) -> list[Event]:
    return read_batch(after)[2]


def read_batch(after=0):
    """Epoch, high-water seq and events from one SQLite read snapshot, under the reset lock."""
    with _lock:
        db = _db()
        db.execute("BEGIN")
        try:
            last_seq = db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
            rows = db.execute("SELECT body FROM events WHERE seq > ? ORDER BY seq",
                              (after,)).fetchall()
            return _epoch, last_seq, [Event.model_validate_json(body) for (body,) in rows]
        finally:
            db.execute("ROLLBACK")


def max_number(prefix):
    """Highest n in any `<prefix>_<n>` in the log: new ids continue from it, so two processes
    writing the same log (API, dev runner, CLI) do not reuse an id."""
    pattern = re.compile(r"\b" + re.escape(prefix) + r"_(\d+)\b")
    with _lock:
        bodies = [b for (b,) in _db().execute("SELECT body FROM events")]
    return max((int(n) for body in bodies for n in pattern.findall(body)), default=0)
