"""Append-only event log. Nothing happens off-log from here on: every turn,
LLM call, tool dispatch, and error is routed through log_event().

Lives in {NALA_DATA_DIR}/events.db, WAL mode. Rows are never updated or
deleted — this table is observability, not application state.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nala.config import get_data_dir

DB_FILENAME = "events.db"


def _connect(data_dir: Path | None = None) -> sqlite3.Connection:
    d = data_dir or get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(d / DB_FILENAME)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn_id TEXT,
            type TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'info',
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)")
    return conn


def new_id() -> str:
    return uuid.uuid4().hex


def ensure_schema(data_dir: Path | None = None) -> None:
    """Ensures the events table exists without writing a row — for callers
    (like nala.briefing) that query it directly via nala.db.connect() and
    need the table to exist even if nothing has been logged yet."""
    _connect(data_dir).close()


def log_event(
    session_id: str,
    turn_id: str | None,
    type_: str,
    payload: dict,
    level: str = "info",
    data_dir: Path | None = None,
) -> int:
    conn = _connect(data_dir)
    ts = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO events (ts, session_id, turn_id, type, level, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, session_id, turn_id, type_, level, json.dumps(payload, default=str)),
    )
    conn.commit()
    event_id = cur.lastrowid
    conn.close()
    return event_id


def last_session_id(data_dir: Path | None = None) -> str | None:
    conn = _connect(data_dir)
    row = conn.execute("SELECT session_id FROM events ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row["session_id"] if row else None


def events_for_session(session_id: str, data_dir: Path | None = None) -> list[sqlite3.Row]:
    conn = _connect(data_dir)
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY id ASC", (session_id,)
    ).fetchall()
    conn.close()
    return rows


def events_for_turn(turn_id: str, data_dir: Path | None = None) -> list[sqlite3.Row]:
    conn = _connect(data_dir)
    rows = conn.execute(
        "SELECT * FROM events WHERE turn_id = ? ORDER BY id ASC", (turn_id,)
    ).fetchall()
    conn.close()
    return rows
