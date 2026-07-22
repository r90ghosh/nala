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


def test_status_endpoint_reports_repos_and_indoubt(monkeypatch, data_dir, tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))
    client = TestClient(app)

    resp = client.get("/api/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "repos" in data
    assert "in_doubt" in data
    assert "message" in data


def test_status_endpoint_is_cached_across_calls(monkeypatch, data_dir, tmp_path):
    import nala.serve as serve_module

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))
    serve_module._status_cache["payload"] = None
    serve_module._status_cache["ts"] = 0.0
    client = TestClient(app)

    first = client.get("/api/status").json()
    calls = {"n": 0}
    real_execute_action = serve_module.chokepoint.execute_action

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real_execute_action(*args, **kwargs)

    monkeypatch.setattr(serve_module.chokepoint, "execute_action", spy)
    second = client.get("/api/status").json()

    assert calls["n"] == 0  # served from cache, report_status never re-ran
    assert first == second


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


def test_static_assets_are_served(data_dir):
    client = TestClient(app)

    css = client.get("/static/style.css")
    js = client.get("/static/app.js")

    assert css.status_code == 200
    assert js.status_code == 200


def test_spend_endpoint_reports_totals_and_breakdown(data_dir):
    from nala import spend as spend_module
    spend_module.record_spend(turn_id="t1", model="claude-sonnet-5", input_tokens=1000, output_tokens=1000)
    client = TestClient(app)

    resp = client.get("/api/spend")

    assert resp.status_code == 200
    data = resp.json()
    assert data["today_total"] > 0
    assert "yesterday_total" in data
    assert "ceiling" in data
    assert any(row["model"] == "claude-sonnet-5" for row in data["by_model"])


def test_health_endpoint_never_blocks_and_reports_watchers(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_OLLAMA_URL", "http://127.0.0.1:1")  # unreachable — must not hang or raise
    client = TestClient(app)

    resp = client.get("/api/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_reachable"] is False
    assert "google_token_ok" in data
    assert set(data["watchers"].keys()) == {"gmail", "calendar", "git"}


def test_routing_endpoint_reflects_real_config(data_dir):
    from nala import routing
    client = TestClient(app)

    resp = client.get("/api/routing")

    assert resp.status_code == 200
    data = resp.json()
    tasks = {row["task"]: row["model"] for row in data}
    assert tasks == {r["task"]: r["model"] for r in routing.get_routes()}


def test_turn_endpoint_runs_process_turn_and_returns_events(data_dir, tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.00")  # ceiling already "reached" — no real API call
    client = TestClient(app)

    resp = client.post("/api/turn", json={"text": "hello"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["turn_id"]
    assert data["status"] == "rejected"  # refused pre-dispatch by the spend ceiling, never hits the real API
    assert any(e["type"] == "utterance" for e in data["events"])


def test_turn_endpoint_requires_text(data_dir):
    client = TestClient(app)

    resp = client.post("/api/turn", json={"text": "  "})

    assert resp.status_code == 400


def test_turn_endpoint_malformed_json_body_is_400_not_500(data_dir):
    client = TestClient(app)

    resp = client.post("/api/turn", content=b"not json at all", headers={"Content-Type": "application/json"})

    assert resp.status_code == 400


def test_status_cache_refresh_tags_events_with_actor_status_cache(monkeypatch, data_dir, tmp_path):
    import nala.serve as serve_module

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))
    serve_module._status_cache["payload"] = None
    serve_module._status_cache["ts"] = 0.0
    client = TestClient(app)

    client.get("/api/status")

    from nala import db
    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'tool_call'").fetchall()
    conn.close()
    assert len(rows) == 1
    import json
    payload = json.loads(rows[0]["payload_json"])
    assert payload["actor"] == "status-cache"
