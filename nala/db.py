"""Shared SQLite connection for the tables introduced in M3
(processed_actions, spend) — same file as events.db, WAL mode. Split out from
chokepoint.py/reconciler.py so both can share one connection helper without
importing each other."""

import sqlite3
from pathlib import Path

from nala.config import get_data_dir

DB_FILENAME = "events.db"


def connect(data_dir: Path | None = None) -> sqlite3.Connection:
    d = data_dir or get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(d / DB_FILENAME)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_processed_actions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_actions (
            idempotency_key TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            reversibility TEXT NOT NULL,
            args_json TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
