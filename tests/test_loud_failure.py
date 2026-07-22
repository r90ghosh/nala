import subprocess

from nala import chokepoint, db
from nala.brain import RawIntent
from nala.tools import report_status as report_status_module


def test_backlog_down_produces_printed_failure_and_error_event(data_dir, fake_backlog):
    fake_backlog.down = True

    result = chokepoint.execute_action(
        "capture_task",
        {"title": "t", "project": "life_os", "priority": "low", "category": "chore"},
        turn_id="turn-down",
        session_id="s1",
    )

    assert result.status == "failed"
    assert "failed" in result.message.lower()

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    assert len(rows) >= 1
    assert any(r["type"] == "error" for r in rows)


def test_report_status_wrong_port_shows_in_doubt_never_all_clear(data_dir, fake_backlog, monkeypatch, tmp_path):
    class SimulatedCrash(Exception):
        pass

    monkeypatch.setattr(
        chokepoint, "_crash_hook",
        lambda cp: (_ for _ in ()).throw(SimulatedCrash()) if cp == "after_pending_commit" else None,
    )
    try:
        chokepoint.execute_action(
            "capture_task",
            {"title": "x", "project": "life_os", "priority": "low", "category": "chore"},
            turn_id="turn-stuck", session_id="s1",
        )
    except SimulatedCrash:
        pass
    monkeypatch.setattr(chokepoint, "_crash_hook", None)

    # "wrong port": point at a backlog url nothing is listening on
    monkeypatch.setenv("NALA_BACKLOG_URL", "http://127.0.0.1:1")
    projects_root = tmp_path / "empty-projects"
    projects_root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(projects_root))

    result = chokepoint.execute_action("report_status", {}, turn_id="turn-report", session_id="s1")

    assert "in-doubt actions: 1" in result.message
    assert "all clear" not in result.message.lower()
    assert "reconciliation failed" in result.message.lower()


def test_report_status_tool_exception_is_caught_logged_and_survives(data_dir, fake_backlog, monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git status --porcelain", timeout=5)

    monkeypatch.setattr(report_status_module.subprocess, "run", boom)

    projects_root = tmp_path / "projects"
    (projects_root / "parentlogs" / ".git").mkdir(parents=True)
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(projects_root))

    # Directly at the chokepoint: the tool call itself must not propagate.
    result = chokepoint.execute_action("report_status", {}, turn_id="turn-boom-1", session_id="s1")

    assert result.status == "failed"
    assert "degraded" in result.message.lower()

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    assert any(r["type"] == "error" for r in rows)

    # And through the REPL's turn-processing path (process_turn) — the
    # session must survive rather than raising out to the caller.
    from nala.cli import process_turn

    class FakeBrain:
        def decide(self, utterance, *, turn_id=None, session_id=None, memory_context=None):
            return RawIntent(action_type="report_status", args={})

    outcome = process_turn("status please", brain=FakeBrain(), session_id="s2")
    assert outcome.status == "failed"
    assert "degraded" in outcome.message.lower()
