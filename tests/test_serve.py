from fastapi.testclient import TestClient

from nala import chokepoint, events
from nala.serve import app


def test_events_endpoint_returns_events_since(data_dir):
    client = TestClient(app)
    events.log_event("s1", "t1", "utterance", {"text": "hi"})
    events.log_event("s1", "t1", "tool_call", {"action_type": "report_status"})

    resp = client.get("/api/events?since=0")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_actions_endpoint_lists_processed_actions(data_dir, fake_backlog):
    client = TestClient(app)
    chokepoint.execute_action(
        "capture_task",
        {"title": "x", "project": "life_os", "priority": "low", "category": "chore"},
        turn_id="t1", session_id="s1",
    )

    resp = client.get("/api/actions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["action_type"] == "capture_task"
    assert data[0]["status"] == "done"


def test_status_endpoint_reports_indoubt_and_spend(data_dir):
    client = TestClient(app)

    resp = client.get("/api/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "in_doubt" in data
    assert "today_spend_usd" in data


def test_confirm_endpoint_dispatches_awaiting_action(data_dir, fake_backlog):
    client = TestClient(app)
    fake_backlog.tasks.append({
        "id": 5, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    first = chokepoint.execute_action("archive_task", {"task_id": 5}, turn_id="t1", session_id="s1")
    token = first.message.rsplit(" ", 1)[-1]

    resp = client.post(f"/api/actions/{token}/confirm")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert fake_backlog.tasks[0]["status"] == "archived"


def test_reject_endpoint_marks_action_rejected_no_dispatch(data_dir, fake_backlog):
    client = TestClient(app)
    fake_backlog.tasks.append({
        "id": 6, "title": "old2", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    first = chokepoint.execute_action("archive_task", {"task_id": 6}, turn_id="t1", session_id="s1")
    token = first.message.rsplit(" ", 1)[-1]

    resp = client.post(f"/api/actions/{token}/reject")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert fake_backlog.tasks[0]["status"] == "backlog"  # never dispatched


def test_confirm_wildcard_token_rejection_parity_with_cli(data_dir, fake_backlog):
    client = TestClient(app)
    fake_backlog.tasks.append({
        "id": 7, "title": "old3", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    chokepoint.execute_action("archive_task", {"task_id": 7}, turn_id="t1", session_id="s1")

    resp = client.post("/api/actions/%25/confirm")  # '%25' is the URL-encoded literal '%'

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert fake_backlog.tasks[0]["status"] == "backlog"  # exploit blocked, no side effect


def test_reject_wildcard_token_rejection_parity_with_cli(data_dir, fake_backlog):
    client = TestClient(app)
    fake_backlog.tasks.append({
        "id": 8, "title": "old4", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    chokepoint.execute_action("archive_task", {"task_id": 8}, turn_id="t1", session_id="s1")

    resp = client.post("/api/actions/%25/reject")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert fake_backlog.tasks[0]["status"] == "backlog"


def test_index_serves_html(data_dir):
    client = TestClient(app)

    resp = client.get("/")

    assert resp.status_code == 200
    assert "Nala" in resp.text
