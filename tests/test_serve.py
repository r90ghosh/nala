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


def test_purposes_endpoint_reflects_real_manifests(data_dir):
    import nala.serve as serve_module
    client = TestClient(app)

    resp = client.get("/api/purposes")

    assert resp.status_code == 200
    data = resp.json()
    assert [p["name"] for p in data] == serve_module.PURPOSE_DISPLAY_ORDER

    by_name = {p["name"]: p for p in data}
    assert by_name["projects"]["risk_profile"] == "act_confirm"
    assert by_name["projects"]["display_name"] == "Projects"
    assert by_name["relationships"]["risk_profile"] == "notify_only"
    assert by_name["finance"]["risk_profile"] == "read_only"


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


def test_memory_endpoint_returns_graph_shape(data_dir):
    from nala import memory
    memory.upsert_node("person", "Priya", "people")

    client = TestClient(app)
    resp = client.get("/api/memory")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["label"] == "Priya"


def test_memory_endpoint_filters_by_purpose_scope(data_dir):
    from nala import memory
    memory.upsert_node("person", "Priya", "people")
    memory.upsert_node("project", "life_os", "projects")

    client = TestClient(app)
    resp = client.get("/api/memory?purpose_scope=people")

    assert resp.status_code == 200
    labels = {n["label"] for n in resp.json()["nodes"]}
    assert labels == {"Priya"}


def test_memory_endpoint_invalid_kind_is_400_not_500(data_dir):
    client = TestClient(app)
    resp = client.get("/api/memory?kind=not_a_real_kind")

    assert resp.status_code == 400
    assert "error" in resp.json()


def test_memory_writes_endpoint_lists_only_memory_write_actions(data_dir, fake_backlog):
    chokepoint.execute_action(
        "capture_task", {"title": "x", "project": "life_os", "priority": "low", "category": "chore"},
        turn_id="t1", session_id="s1",
    )
    chokepoint.execute_action(
        "memory_write", {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "people"},
        turn_id="t2", session_id="s1",
    )

    client = TestClient(app)
    resp = client.get("/api/memory/writes")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["action_type"] == "memory_write"


def test_memory_undo_endpoint_deletes_the_node(data_dir):
    result = chokepoint.execute_action(
        "memory_write", {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "people"},
        turn_id="t1", session_id="s1",
    )
    node_id = result.data["node_id"]

    client = TestClient(app)
    resp = client.post(f"/api/memory/undo/{node_id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "done"

    from nala import memory
    assert memory.query(label="Priya")["nodes"] == []


def test_dismiss_endpoint_marks_notified_action_dismissed(data_dir):
    chokepoint.execute_action(
        "memory_write", {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "people"},
        turn_id="t1", session_id="s1", purpose="relationships",
    )
    rows = chokepoint.list_processed_actions()
    token = rows[0]["idempotency_key"][:8]

    client = TestClient(app)
    resp = client.post(f"/api/actions/{token}/dismiss")

    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"


def _make_wav_bytes(duration_ms=1000, rate=16000):
    import io
    import wave
    n = int(rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


class _FakeVoiceBrain:
    def decide(self, utterance, *, turn_id=None, session_id=None, memory_context=None):
        from nala.brain import RawIntent
        return RawIntent(action_type="report_status", args={})


def test_voice_warmup_endpoint_calls_voice_warmup(monkeypatch, data_dir):
    import nala.serve as serve_module
    calls = []
    monkeypatch.setattr(serve_module.voice, "warmup", lambda: calls.append(True))

    client = TestClient(app)
    resp = client.get("/api/voice/warmup")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert calls == [True]


def test_voice_turn_happy_path(monkeypatch, data_dir, tmp_path):
    import nala.serve as serve_module
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    monkeypatch.setattr(
        serve_module.voice, "transcribe",
        lambda path, **kw: {"text": "what's the status", "duration_ms": 1000, "latency_ms": 50, "confidence": 0.95},
    )
    monkeypatch.setattr(serve_module.voice, "synthesize", lambda text, **kw: b"FAKEREPLYWAV")
    monkeypatch.setattr(serve_module, "Brain", _FakeVoiceBrain)

    client = TestClient(app)
    resp = client.post("/api/voice/turn", files={"audio": ("a.wav", _make_wav_bytes(), "audio/wav")})

    assert resp.status_code == 200
    data = resp.json()
    assert data["transcript"] == "what's the status"
    assert data["status"] == "done"
    assert "turn_id" in data

    import base64
    assert base64.b64decode(data["audio_b64"]) == b"FAKEREPLYWAV"


def test_voice_turn_ask_repeat_path_never_runs_process_turn(monkeypatch, data_dir):
    import nala.serve as serve_module

    monkeypatch.setattr(
        serve_module.voice, "transcribe",
        lambda path, **kw: {"text": "", "duration_ms": 1000, "latency_ms": 10, "confidence": None},
    )
    called = []
    monkeypatch.setattr(serve_module, "_run_turn_sync", lambda *a, **kw: called.append(True))

    client = TestClient(app)
    resp = client.post("/api/voice/turn", files={"audio": ("a.wav", _make_wav_bytes(), "audio/wav")})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ask_repeat"] is True
    assert called == []


def test_voice_turn_missing_audio_is_400(data_dir):
    client = TestClient(app)

    resp = client.post("/api/voice/turn", data={})

    assert resp.status_code == 400


def test_voice_turn_malformed_audio_is_400(data_dir):
    client = TestClient(app)

    resp = client.post("/api/voice/turn", files={"audio": ("a.wav", b"not a real wav file", "audio/wav")})

    assert resp.status_code == 400


def test_voice_turn_oversized_bytes_is_413(data_dir):
    import nala.serve as serve_module
    client = TestClient(app)

    resp = client.post(
        "/api/voice/turn",
        files={"audio": ("a.wav", b"\x00" * (serve_module.MAX_VOICE_AUDIO_BYTES + 1), "audio/wav")},
    )

    assert resp.status_code == 413


def test_voice_turn_oversized_duration_is_413(data_dir):
    client = TestClient(app)
    long_wav = _make_wav_bytes(duration_ms=20_000, rate=8000)  # well under the byte limit, over the duration limit

    resp = client.post("/api/voice/turn", files={"audio": ("a.wav", long_wav, "audio/wav")})

    assert resp.status_code == 413


def test_voice_turn_requires_auth_over_tunnel(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app)

    resp = client.post(
        "/api/voice/turn",
        files={"audio": ("a.wav", _make_wav_bytes(), "audio/wav")},
        headers={"cf-connecting-ip": "1.2.3.4"},
    )

    assert resp.status_code == 401
