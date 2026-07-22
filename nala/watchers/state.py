"""Per-watcher watermark ('last-seen cursor'), so a poll only turns genuinely
NEW items into signals — never re-signals something already seen. Stored as
JSON in a small `watermarks` table in the same events.db file; each watcher
owns its own cursor shape (gmail: a historyId, calendar: signaled event ids
+ start times, git: last-known per-repo branch/dirty/ahead/behind)."""

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


def get_cursor(watcher: str, data_dir: Path | None = None) -> dict:
    conn = connect(data_dir)
    try:
        _ensure(conn)
        row = conn.execute("SELECT cursor_json FROM watermarks WHERE watcher = ?", (watcher,)).fetchone()
        return json.loads(row["cursor_json"]) if row else {}
    finally:
        conn.close()


def set_cursor(watcher: str, cursor: dict, data_dir: Path | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(data_dir)
    try:
        _ensure(conn)
        conn.execute(
            "INSERT INTO watermarks (watcher, cursor_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(watcher) DO UPDATE SET cursor_json=excluded.cursor_json, updated_at=excluded.updated_at",
            (watcher, json.dumps(cursor), now),
        )
        conn.commit()
    finally:
        conn.close()
