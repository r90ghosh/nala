"""Proactive proposals (triage, force_confirm=True) must be distinguishable
from user-initiated awaiting_confirm actions on the confirm surface — a
prompt-injected email can't be allowed to look identical to something the
operator asked for directly."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from nala import chokepoint, events, triage
from nala.cli import render_pending
from nala.serve import app

HOSTILE_SUBJECT = 'Hostile <script>alert(1)</script> subject'


def _make_signal_event(ref="r1", source="gmail", title=HOSTILE_SUBJECT, detail="d", data_dir=None):
    return events.log_event(
        "test-session", None, "signal",
        {"source": source, "kind": "new_message", "title": title, "detail": detail, "ref": ref},
        data_dir=data_dir,
    )


def _propose_via_triage(fake_ollama, reason="worth doing"):
    _make_signal_event()
    fake_ollama.responses.append(json.dumps({
        "classification": "propose",
        "reason": reason,
        "capture_task": {"title": "t", "project": "life_os", "priority": "low", "category": "chore"},
    }))
    return triage.run_triage_pass()


def test_derive_origin_for_proactive_proposal(data_dir, fake_backlog, fake_ollama):
    _propose_via_triage(fake_ollama, reason="looks like <b>spam</b> but flagging anyway")

    rows = chokepoint.list_processed_actions()
    awaiting = [r for r in rows if r["status"] == "awaiting_confirm"]
    assert len(awaiting) == 1

    origin = awaiting[0]["origin"]
    assert origin["kind"] == "proactive"
    assert origin["source"] == "gmail"
    assert origin["model"] == "llama3.2:3b"
    assert "spam" in origin["reason"]
    assert origin["signal_title"] == HOSTILE_SUBJECT  # raw at the API layer — escaping is the client's job


def test_derive_origin_for_user_initiated_action(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 9, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    chokepoint.execute_action("archive_task", {"task_id": 9}, turn_id="user-turn-1", session_id="s1")

    rows = chokepoint.list_processed_actions()
    awaiting = [r for r in rows if r["status"] == "awaiting_confirm"]
    assert len(awaiting) == 1
    assert awaiting[0]["origin"]["kind"] == "user"


def test_api_actions_endpoint_includes_origin_for_proactive_and_user_rows(data_dir, fake_backlog, fake_ollama):
    _propose_via_triage(fake_ollama)
    fake_backlog.tasks.append({
        "id": 9, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    chokepoint.execute_action("archive_task", {"task_id": 9}, turn_id="user-turn-1", session_id="s1")

    client = TestClient(app)
    resp = client.get("/api/actions")
    assert resp.status_code == 200
    awaiting = [r for r in resp.json() if r["status"] == "awaiting_confirm"]

    kinds = {r["origin"]["kind"] for r in awaiting}
    assert kinds == {"proactive", "user"}


def test_confirm_message_includes_origin_line_for_proactive_proposal(data_dir, fake_backlog, fake_ollama):
    _propose_via_triage(fake_ollama, reason="worth doing")

    rows = chokepoint.list_processed_actions()
    token = rows[0]["idempotency_key"][:8]

    result = chokepoint.confirm_action(token, turn_id="t2", session_id="s1")

    assert "proposed by llama3.2:3b" in result.message
    assert "worth doing" in result.message


def test_confirm_message_has_no_origin_line_for_user_initiated_action(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 9, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    first = chokepoint.execute_action("archive_task", {"task_id": 9}, turn_id="t1", session_id="s1")
    token = first.message.rsplit(" ", 1)[-1]

    result = chokepoint.confirm_action(token, turn_id="t2", session_id="s1")

    assert "proposed by" not in result.message


def test_render_pending_shows_origin_for_proactive_proposal(data_dir, fake_backlog, fake_ollama):
    _propose_via_triage(fake_ollama, reason="worth doing")

    text = render_pending()

    assert "proposed by llama3.2:3b" in text
    assert "worth doing" in text


def test_render_pending_shows_user_initiated_for_direct_action(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 9, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    chokepoint.execute_action("archive_task", {"task_id": 9}, turn_id="user-turn-1", session_id="s1")

    text = render_pending()

    assert "user-initiated" in text


def test_index_html_escapes_all_origin_fields():
    html = (Path(__file__).parent.parent / "nala" / "static" / "index.html").read_text()
    assert "esc(origin.model" in html
    assert "esc(origin.source" in html
    assert "esc(origin.signal_title" in html
    assert "esc(origin.reason" in html
