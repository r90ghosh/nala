import json

from nala import chokepoint, db, events, state, triage
from nala.db import ensure_processed_actions


def _make_signal_event(ref="r1", source="git", kind="newly_dirty", title="t", detail="d", data_dir=None):
    return events.log_event(
        "test-session", None, "signal",
        {"source": source, "kind": kind, "title": title, "detail": detail, "ref": ref},
        data_dir=data_dir,
    )


def test_ignore_classification_is_logged_and_watermark_advances(data_dir, fake_ollama):
    event_id = _make_signal_event()
    fake_ollama.responses.append(json.dumps({"classification": "ignore", "reason": "not important", "capture_task": None}))

    counts = triage.run_triage_pass()

    assert counts == {"triaged": 1, "proposed": 0, "rejected": 0}

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'triage'").fetchall()
    conn.close()
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload_json"])
    assert payload["classification"] == "ignore"

    assert state.get_cursor("triage")["last_event_id"] == event_id


def test_propose_with_valid_args_routes_to_awaiting_confirm_not_dispatched(data_dir, fake_backlog, fake_ollama):
    _make_signal_event(source="git", kind="dirty_or_diverged", title="life_os: dirty", ref="life_os")
    fake_ollama.responses.append(json.dumps({
        "classification": "propose",
        "reason": "uncommitted work should be tracked",
        "capture_task": {"title": "commit WIP in life_os", "project": "life_os", "priority": "low", "category": "chore"},
    }))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 1
    assert len(fake_backlog.tasks) == 0  # not dispatched yet — awaiting confirm, even though capture_task is reversible

    conn = db.connect()
    row = conn.execute("SELECT * FROM processed_actions WHERE status = 'awaiting_confirm'").fetchone()
    conn.close()
    assert row is not None
    assert row["action_type"] == "capture_task"

    result = chokepoint.confirm_action(row["idempotency_key"][:8], turn_id="t-confirm", session_id="s1")

    assert result.status == "done"
    assert len(fake_backlog.tasks) == 1


def test_propose_with_invalid_project_is_rejected_by_chokepoint_not_auto_executed(data_dir, fake_backlog, fake_ollama):
    _make_signal_event()
    fake_ollama.responses.append(json.dumps({
        "classification": "propose",
        "reason": "bad project name from the model",
        "capture_task": {"title": "x", "project": "last mile", "priority": "low", "category": "chore"},
    }))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 1  # we did attempt it — chokepoint is what rejected it
    assert len(fake_backlog.tasks) == 0

    conn = db.connect()
    ensure_processed_actions(conn)  # rejections never create the row, but may never have created the table either
    rows = conn.execute("SELECT * FROM processed_actions").fetchall()
    conn.close()
    assert len(rows) == 0  # boundary rejection never creates a ledger row


def test_malformed_model_output_is_rejected_loudly_and_watermark_still_advances(data_dir, fake_ollama):
    _make_signal_event(ref="a")
    id2 = _make_signal_event(ref="b")
    fake_ollama.responses.append("this is not json at all")
    fake_ollama.responses.append(json.dumps({"classification": "ignore", "reason": "fine"}))

    counts = triage.run_triage_pass()

    assert counts["rejected"] == 1
    assert counts["triaged"] == 1

    conn = db.connect()
    error_rows = conn.execute("SELECT * FROM events WHERE type = 'triage' AND level = 'error'").fetchall()
    conn.close()
    assert len(error_rows) == 1

    assert state.get_cursor("triage")["last_event_id"] == id2


def test_ollama_unreachable_is_loud_and_leaves_signal_untriaged(data_dir, fake_ollama):
    _make_signal_event()
    fake_ollama.down = True

    counts = triage.run_triage_pass()

    assert counts == {"triaged": 0, "proposed": 0, "rejected": 0}

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    assert any(r["type"] == "error" for r in rows)

    # Watermark must NOT have advanced — the signal stays un-triaged for retry.
    assert state.get_cursor("triage") == {}


def test_repoll_does_not_reprocess_already_triaged_signals(data_dir, fake_ollama):
    _make_signal_event()
    fake_ollama.responses.append(json.dumps({"classification": "remember", "reason": "context"}))

    triage.run_triage_pass()
    assert fake_ollama.calls == 1

    counts = triage.run_triage_pass()

    assert counts == {"triaged": 0, "proposed": 0, "rejected": 0}
    assert fake_ollama.calls == 1  # second pass never even called Ollama — nothing new to triage
