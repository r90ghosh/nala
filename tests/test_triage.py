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


def test_propose_with_no_determined_purpose_routes_to_notified_not_dispatched(data_dir, fake_backlog, fake_ollama):
    # No "purpose" in the model's output — an unassigned purpose is gated as
    # notify_only (the conservative default), never as if it were a direct
    # user turn (which would dispatch a reversible action immediately).
    _make_signal_event(source="git", kind="dirty_or_diverged", title="life_os: dirty", ref="life_os")
    fake_ollama.responses.append(json.dumps({
        "classification": "propose",
        "reason": "uncommitted work should be tracked",
        "capture_task": {"title": "commit WIP in life_os", "project": "life_os", "priority": "low", "category": "chore"},
    }))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 1
    assert len(fake_backlog.tasks) == 0  # not dispatched — notified, no side effect

    conn = db.connect()
    row = conn.execute("SELECT * FROM processed_actions WHERE status = 'notified'").fetchone()
    conn.close()
    assert row is not None
    assert row["action_type"] == "capture_task"


def test_propose_with_projects_purpose_routes_to_awaiting_confirm_then_dispatches(data_dir, fake_backlog, fake_ollama):
    _make_signal_event(source="git", kind="dirty_or_diverged", title="life_os: dirty", ref="life_os")
    fake_ollama.responses.append(json.dumps({
        "classification": "propose",
        "purpose": "projects",
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


def test_watermark_commits_incrementally_per_signal_not_once_per_batch(data_dir, fake_ollama, monkeypatch):
    id1 = _make_signal_event(ref="sig1")
    id2 = _make_signal_event(ref="sig2")
    fake_ollama.responses.append(json.dumps({"classification": "ignore", "reason": "r1"}))
    fake_ollama.responses.append(json.dumps({"classification": "ignore", "reason": "r2"}))

    committed = []
    real_set_cursor = state.set_cursor

    def spy_set_cursor(name, cursor, data_dir=None):
        if name == triage.WATERMARK_NAME:
            committed.append(cursor.get("last_event_id"))
        return real_set_cursor(name, cursor, data_dir)

    monkeypatch.setattr(triage.state, "set_cursor", spy_set_cursor)

    triage.run_triage_pass()

    assert committed == [id1, id2]  # incremental — one commit per signal, not a single final commit


def test_mid_batch_failure_does_not_reprocess_already_handled_signal(data_dir, fake_ollama):
    id1 = _make_signal_event(ref="sig1")
    _make_signal_event(ref="sig2")
    fake_ollama.responses.append(json.dumps({"classification": "ignore", "reason": "r1"}))
    # No second response queued: signal 2's turn hits the empty-queue 503,
    # simulating Ollama going down (or the process crashing) mid-batch.

    counts = triage.run_triage_pass()

    assert counts["triaged"] == 1
    assert state.get_cursor("triage")["last_event_id"] == id1  # committed past signal 1 already
    calls_after_first_pass = fake_ollama.calls  # 2: signal 1 succeeded, signal 2 hit the empty queue

    # A later pass must only see signal 2 remaining — signal 1 is durably
    # handled and is never re-triaged into a duplicate awaiting_confirm row.
    fake_ollama.responses.append(json.dumps({"classification": "remember", "reason": "r2"}))
    counts2 = triage.run_triage_pass()

    assert counts2["triaged"] == 1
    assert fake_ollama.calls == calls_after_first_pass + 1  # exactly one more call — for signal 2, never signal 1 again


def test_remember_person_proposes_memory_write_in_people_scope_regardless_of_purpose(data_dir, fake_ollama):
    # No purpose determined, but a person-kind fact is ALWAYS placeable in
    # the shared 'people' scope — this must still get a chance to propose,
    # rather than being rejected outright for lacking a purpose. It's still
    # gated like any other proactive write though: unknown purpose falls
    # back to notify_only, so it lands as a 'notified' row, not an immediate
    # write.
    _make_signal_event(source="imessage", title="Priya mentioned she loves ceramics")
    fake_ollama.responses.append(json.dumps({
        "classification": "remember",
        "reason": "worth remembering",
        "memory_write": {"kind": "person", "label": "Priya", "fact": "loves ceramics"},
    }))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 1

    from nala import memory
    assert memory.query(label="Priya")["nodes"] == []  # notified, no side effect yet

    conn = db.connect()
    ensure_processed_actions(conn)
    row = conn.execute("SELECT * FROM processed_actions WHERE status = 'notified'").fetchone()
    conn.close()
    assert row is not None
    assert row["action_type"] == "memory_write"
    assert json.loads(row["args_json"])["purpose_scope"] == "people"


def test_remember_non_person_with_known_purpose_proposes_memory_write(data_dir, fake_ollama):
    _make_signal_event(source="gmail", title="Netflix receipt")
    fake_ollama.responses.append(json.dumps({
        "classification": "remember",
        "purpose": "finance",
        "reason": "subscription worth tracking",
        "memory_write": {"kind": "thing", "label": "Netflix", "fact": "monthly subscription"},
    }))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 1

    from nala import memory
    result = memory.query(label="Netflix")
    # finance is read_only — the write is rejected loudly per the risk
    # gating matrix, not silently dropped, and never actually lands.
    assert result["nodes"] == []

    conn = db.connect()
    ensure_processed_actions(conn)
    rows = conn.execute("SELECT * FROM processed_actions WHERE action_type = 'memory_write'").fetchall()
    conn.close()
    assert len(rows) == 0  # read_only rejection happens in the gate, before any ledger row is created


def test_remember_non_person_with_unknown_purpose_is_rejected_no_write_attempted(data_dir, fake_ollama):
    _make_signal_event(source="gmail", title="some receipt")
    fake_ollama.responses.append(json.dumps({
        "classification": "remember",
        "reason": "unclear what this is",
        "memory_write": {"kind": "thing", "label": "Mystery Item", "fact": "appeared in an email"},
    }))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 0  # never even attempted — no determinable purpose_scope

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'rejected' AND level = 'error'").fetchall()
    conn.close()
    assert any("purpose_scope" in r["payload_json"] for r in rows)

    from nala import memory
    assert memory.query(label="Mystery Item")["nodes"] == []


def test_remember_missing_memory_write_fields_is_rejected_loudly(data_dir, fake_ollama):
    _make_signal_event()
    fake_ollama.responses.append(json.dumps({"classification": "remember", "reason": "vague", "memory_write": None}))

    counts = triage.run_triage_pass()

    assert counts["proposed"] == 0
    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'rejected' AND level = 'error'").fetchall()
    conn.close()
    assert any("memory_write" in r["payload_json"] for r in rows)
