"""Resolves in-doubt (still-pending) processed_actions rows against the
backlog, the source of truth for capture_task. Run at startup and before
every report_status. If the backlog itself is unreachable, rows are left
pending (still in-doubt) rather than guessed at — the caller decides how to
surface that."""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from nala import events
from nala.config import get_backlog_url
from nala.db import connect, ensure_processed_actions


def in_doubt_count(data_dir: Path | None = None) -> int:
    conn = connect(data_dir)
    ensure_processed_actions(conn)
    row = conn.execute("SELECT COUNT(*) AS cnt FROM processed_actions WHERE status = 'pending'").fetchone()
    conn.close()
    return row["cnt"]


def reconcile(
    data_dir: Path | None = None,
    session_id: str = "reconciler",
    turn_id: str = "reconciler",
) -> dict:
    conn = connect(data_dir)
    ensure_processed_actions(conn)
    pending = conn.execute(
        "SELECT * FROM processed_actions WHERE status = 'pending' AND action_type = 'capture_task'"
    ).fetchall()

    if not pending:
        conn.close()
        return {"resolved_done": 0, "resolved_failed": 0, "still_pending": 0}

    resp = httpx.get(f"{get_backlog_url()}/api/tasks", timeout=10)
    resp.raise_for_status()
    tasks = resp.json()

    resolved_done = 0
    resolved_failed = 0
    now = datetime.now(timezone.utc).isoformat()

    to_log = []  # (turn_id, key, error) — logged after conn is committed and closed,
                 # so the events.log_event() connection never contends with this one.

    for row in pending:
        key = row["idempotency_key"]
        match = next((t for t in tasks if f"[ref:{key}]" in (t.get("description") or "")), None)
        if match is not None:
            conn.execute(
                "UPDATE processed_actions SET status='done', result_json=?, resolved_at=? WHERE idempotency_key=?",
                (json.dumps(match), now, key),
            )
            resolved_done += 1
        else:
            error = {"reason": "no matching task found in backlog after restart; action presumed lost"}
            conn.execute(
                "UPDATE processed_actions SET status='failed', error_json=?, resolved_at=? WHERE idempotency_key=?",
                (json.dumps(error), now, key),
            )
            to_log.append((row["turn_id"], key, error))
            resolved_failed += 1

    conn.commit()
    conn.close()

    for turn_id, key, error in to_log:
        events.log_event(
            session_id, turn_id, "error",
            {"context": "reconciler", "idempotency_key": key, **error},
            level="error", data_dir=data_dir,
        )

    return {
        "resolved_done": resolved_done,
        "resolved_failed": resolved_failed,
        "still_pending": in_doubt_count(data_dir),
    }
