"""Risk-profile enforcement matrix: read_only/notify_only/act_confirm ×
read-tool/write-tool. Read tools (report_status, memory_recall) always
bypass gating regardless of purpose; write tools get gated per the
purpose's risk_profile. purpose=None (a direct user turn) is unaffected —
risk profiles gate PROACTIVE actions only."""

from nala import chokepoint, db


def _memory_write_args():
    return {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "people"}


# ---------------------------------------------------------------- read_only

def test_read_only_purpose_write_tool_rejected_no_side_effect(data_dir):
    result = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t1", session_id="s1", purpose="finance",
    )
    assert result.status == "rejected"

    from nala import memory
    assert memory.query(label="Priya")["nodes"] == []


def test_read_only_purpose_read_tool_still_allowed(data_dir):
    result = chokepoint.execute_action(
        "memory_recall", {}, turn_id="t2", session_id="s1", purpose="finance",
    )
    assert result.status == "done"


# ---------------------------------------------------------------- notify_only

def test_notify_only_purpose_write_tool_creates_notified_row_no_side_effect(data_dir):
    result = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t3", session_id="s1", purpose="relationships",
    )
    assert result.status == "notified"

    from nala import memory
    assert memory.query(label="Priya")["nodes"] == []  # no side effect — the whole point of notify_only


def test_notify_only_purpose_read_tool_still_allowed(data_dir):
    result = chokepoint.execute_action(
        "memory_recall", {}, turn_id="t4", session_id="s1", purpose="baby",
    )
    assert result.status == "done"


# ---------------------------------------------------------------- act_confirm

def test_act_confirm_purpose_write_tool_awaits_confirmation_no_side_effect(data_dir):
    result = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t5", session_id="s1", purpose="projects",
    )
    assert result.status == "awaiting_confirm"

    from nala import memory
    assert memory.query(label="Priya")["nodes"] == []


def test_act_confirm_purpose_read_tool_still_allowed(data_dir):
    result = chokepoint.execute_action(
        "report_status", {}, turn_id="t6", session_id="s1", purpose="home",
    )
    assert result.status in ("done", "failed")  # report_status's own status, gating doesn't apply to reads


def test_act_confirm_purpose_write_confirmed_then_dispatches(data_dir):
    proposal = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t7", session_id="s1", purpose="projects",
    )
    assert proposal.status == "awaiting_confirm"

    rows = chokepoint.list_processed_actions()
    token = rows[0]["idempotency_key"][:8]

    confirmed = chokepoint.confirm_action(token, turn_id="t8", session_id="s1")
    assert confirmed.status == "done"

    from nala import memory
    assert len(memory.query(label="Priya")["nodes"]) == 1


# ---------------------------------------------------------------- unknown purpose

def test_unknown_purpose_treated_as_notify_only_never_guessed_permissive(data_dir):
    result = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t9", session_id="s1", purpose="not_a_real_purpose",
    )
    assert result.status == "notified"  # never rejected (read_only) or auto-confirmed (act_confirm) — the conservative default


# ---------------------------------------------------------------- direct user turns unaffected

def test_direct_user_turn_purpose_none_dispatches_reversible_immediately(data_dir):
    result = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t10", session_id="s1",
    )
    assert result.status == "done"  # no purpose given — ordinary reversible-action behavior, unaffected by risk profiles


# ---------------------------------------------------------------- malformed manifest resilience

def test_malformed_manifest_during_dispatch_is_rejected_loudly_not_raised(data_dir, monkeypatch):
    from nala import chokepoint as chokepoint_module
    from nala import purposes

    def boom(purpose, purposes_dir=None):
        raise purposes.PurposeManifestError("manifest mid-edit — invalid YAML")

    monkeypatch.setattr(chokepoint_module.purposes, "risk_profile_for", boom)

    result = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t18", session_id="s1", purpose="projects",
    )

    assert result.status == "rejected"
    assert "risk profile" in result.message.lower()

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    assert any("purpose risk-profile lookup" in r["payload_json"] for r in rows)

    # No side effect and no ledger row — the failure happened before dispatch.
    from nala import memory
    assert memory.query(label="Priya")["nodes"] == []


# ---------------------------------------------------------------- dismiss lifecycle

def test_dismiss_notified_action_marks_dismissed(data_dir):
    proposal = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t11", session_id="s1", purpose="relationships",
    )
    assert proposal.status == "notified"

    rows = chokepoint.list_processed_actions()
    token = rows[0]["idempotency_key"][:8]

    dismissed = chokepoint.dismiss_action(token, turn_id="t12", session_id="s1")
    assert dismissed.status == "dismissed"

    conn = db.connect()
    from nala.db import ensure_processed_actions
    ensure_processed_actions(conn)
    row = conn.execute("SELECT status FROM processed_actions WHERE idempotency_key LIKE ?", (f"{token}%",)).fetchone()
    conn.close()
    assert row["status"] == "dismissed"


def test_dismiss_wildcard_token_rejected(data_dir):
    chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t13", session_id="s1", purpose="relationships",
    )
    result = chokepoint.dismiss_action("%", turn_id="t14", session_id="s1")
    assert result.status == "rejected"


def test_dismiss_no_match_rejected(data_dir):
    result = chokepoint.dismiss_action("deadbeef", turn_id="t15", session_id="s1")
    assert result.status == "rejected"


def test_dismiss_does_not_match_awaiting_confirm_rows(data_dir):
    # A dismiss token must only resolve 'notified' rows, never 'awaiting_confirm' ones.
    proposal = chokepoint.execute_action(
        "memory_write", _memory_write_args(), turn_id="t16", session_id="s1", purpose="projects",
    )
    assert proposal.status == "awaiting_confirm"

    rows = chokepoint.list_processed_actions()
    token = rows[0]["idempotency_key"][:8]

    result = chokepoint.dismiss_action(token, turn_id="t17", session_id="s1")
    assert result.status == "rejected"
