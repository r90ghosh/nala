"""Named watermark ('last-seen cursor') storage, so a poll or pass only
processes genuinely NEW items — never re-processes something already seen.
Stored as JSON in a small `watermarks` table in the same events.db file.
Used by watchers (gmail: a historyId, calendar: signaled event ids + start
times, git: last-known per-repo branch/dirty/ahead/behind) and by triage
(last-triaged signal event id) — anything that needs "where did I leave
off" state keyed by its own name."""

import json
from datetime import datetime, timezone
from pathlib import Path

from nala.db import connect


def _ensure(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watermarks (
            watcher TEXT PRIMARY KEY,
            cursor_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def get_cursor(name: str, data_dir: Path | None = None) -> dict:
    conn = connect(data_dir)
    try:
        _ensure(conn)
        row = conn.execute("SELECT cursor_json FROM watermarks WHERE watcher = ?", (name,)).fetchone()
        return json.loads(row["cursor_json"]) if row else {}
    finally:
        conn.close()


def set_cursor(name: str, cursor: dict, data_dir: Path | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(data_dir)
    try:
        _ensure(conn)
        conn.execute(
            "INSERT INTO watermarks (watcher, cursor_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(watcher) DO UPDATE SET cursor_json=excluded.cursor_json, updated_at=excluded.updated_at",
            (name, json.dumps(cursor), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_updated_at(name: str, data_dir: Path | None = None) -> str | None:
    """Last time this name's cursor was written — used as "last poll" for
    watcher health display."""
    conn = connect(data_dir)
    try:
        _ensure(conn)
        row = conn.execute("SELECT updated_at FROM watermarks WHERE watcher = ?", (name,)).fetchone()
        return row["updated_at"] if row else None
    finally:
        conn.close()
