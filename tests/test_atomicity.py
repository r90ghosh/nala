import json
from datetime import datetime, timezone

import httpx
import pytest

from nala import chokepoint, db, reconciler, validation
from nala.config import get_backlog_url


class SimulatedCrash(Exception):
    pass


def test_crash_before_post_resolves_to_failed(data_dir, fake_backlog, monkeypatch):
    def crash_hook(checkpoint):
        if checkpoint == "after_pending_commit":
            raise SimulatedCrash()

    monkeypatch.setattr(chokepoint, "_crash_hook", crash_hook)

    with pytest.raises(SimulatedCrash):
        chokepoint.execute_action(
            "capture_task",
            {"title": "t1", "project": "life_os", "priority": "low", "category": "chore"},
            turn_id="turn-crash-1",
            session_id="s",
        )

    monkeypatch.setattr(chokepoint, "_crash_hook", None)

    assert len(fake_backlog.tasks) == 0  # crashed before the POST ever happened
    assert reconciler.in_doubt_count() == 1  # in-doubt until reconciled

    result = reconciler.reconcile()
    assert result["resolved_failed"] == 1
    assert result["resolved_done"] == 0
    assert reconciler.in_doubt_count() == 0


def test_crash_after_post_resolves_to_done(data_dir, fake_backlog, monkeypatch):
    def crash_hook(checkpoint):
        if checkpoint == "after_side_effect":
            raise SimulatedCrash()

    monkeypatch.setattr(chokepoint, "_crash_hook", crash_hook)

    with pytest.raises(SimulatedCrash):
        chokepoint.execute_action(
            "capture_task",
            {"title": "t2", "project": "life_os", "priority": "low", "category": "chore"},
            turn_id="turn-crash-2",
            session_id="s",
        )

    monkeypatch.setattr(chokepoint, "_crash_hook", None)

    assert len(fake_backlog.tasks) == 1  # the side effect landed before the "crash"
    assert reconciler.in_doubt_count() == 1

    result = reconciler.reconcile()
    assert result["resolved_done"] == 1
    assert result["resolved_failed"] == 0
    assert reconciler.in_doubt_count() == 0


def test_lost_insert_race_replays_instead_of_double_dispatch(data_dir, fake_backlog, monkeypatch):
    """Two concurrent same-key callers can both pass the initial SELECT before
    either commits. The second one to reach INSERT OR IGNORE must detect it
    lost the race (via cur.rowcount) and replay the winner's result instead
    of dispatching its own POST."""
    args = {"title": "race condition", "project": "life_os", "priority": "low", "category": "chore"}
    turn_id = "turn-race"

    validated = validation.validate_intent("capture_task", args)
    normalized_args = validated.model_dump(exclude={"action_type"})
    key = chokepoint.compute_key("capture_task", normalized_args, turn_id)

    def hook(checkpoint_name):
        if checkpoint_name != "before_insert":
            return
        # Simulate a concurrent caller that wins the insert and fully
        # completes the side effect in the window between our SELECT and
        # our own INSERT OR IGNORE.
        now = datetime.now(timezone.utc).isoformat()
        other_conn = db.connect()
        db.ensure_processed_actions(other_conn)
        other_conn.execute(
            "INSERT OR IGNORE INTO processed_actions "
            "(idempotency_key, turn_id, action_type, reversibility, args_json, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (key, turn_id, "capture_task", "reversible", json.dumps(normalized_args), "pending", now),
        )
        other_conn.commit()
        other_conn.close()

        resp = httpx.post(
            f"{get_backlog_url()}/api/tasks",
            json={**normalized_args, "description": f"[ref:{key}]"},
            timeout=10,
        )
        task = resp.json()

        done_conn = db.connect()
        db.ensure_processed_actions(done_conn)
        done_conn.execute(
            "UPDATE processed_actions SET status='done', result_json=?, resolved_at=? WHERE idempotency_key=?",
            (json.dumps(task), now, key),
        )
        done_conn.commit()
        done_conn.close()

    monkeypatch.setattr(chokepoint, "_crash_hook", hook)
    result = chokepoint.execute_action("capture_task", args, turn_id=turn_id, session_id="s1")
    monkeypatch.setattr(chokepoint, "_crash_hook", None)

    assert len(fake_backlog.tasks) == 1  # only the "concurrent winner"'s POST happened
    assert result.status == "done"
    assert "replayed" in result.message.lower()

    conn = db.connect()
    rows = conn.execute("SELECT * FROM processed_actions WHERE idempotency_key = ?", (key,)).fetchall()
    conn.close()
    assert len(rows) == 1  # never a second row for the same key
