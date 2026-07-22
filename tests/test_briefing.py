import json

from nala import briefing, db, events, spend


def test_calendar_unavailable_without_token_is_a_known_unknown(data_dir):
    text = briefing._fetch_todays_calendar("s1", "t1", None)

    assert "known-unknown" in text
    assert "calendar unavailable" in text


def test_repo_status_section_reuses_chokepoint(monkeypatch, data_dir, tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    text = briefing._fetch_repo_status("s1", "t1", None)

    assert "in-doubt actions:" in text


def test_activity_summary_empty_when_no_recent_events(data_dir):
    text = briefing._fetch_activity_summary("s1", "t1", None)

    assert text == "no new signals or triage activity in the last 24h"


def test_activity_summary_counts_signals_and_triage(data_dir):
    events.log_event("s1", None, "signal", {"source": "git", "kind": "newly_dirty", "title": "t", "detail": "d", "ref": "r1"})
    events.log_event("s1", "t1", "triage", {"signal_event_id": 1, "classification": "propose", "reason": "r", "model": "llama3.2:3b"})

    text = briefing._fetch_activity_summary("s1", "t1", None)

    assert "git" in text
    assert "propose" in text


def test_spend_summary_reports_yesterday_and_today(data_dir):
    spend.record_spend(turn_id="t1", model="claude-sonnet-5", input_tokens=1000, output_tokens=1000)

    text = briefing._fetch_spend_summary("s1", "t1", None)

    assert "yesterday" in text
    assert "today so far" in text
    assert "$0.0180" in text  # 1000/1e6*3 + 1000/1e6*15 = 0.018


def test_summarize_falls_back_to_raw_material_when_ceiling_exceeded(data_dir, monkeypatch):
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.01")
    spend.record_spend(turn_id="prior", model="claude-sonnet-5", input_tokens=100_000, output_tokens=100_000)

    text = briefing._summarize("RAW MATERIAL MARKER", "t1", None)

    assert "spend ceiling reached" in text
    assert "RAW MATERIAL MARKER" in text  # never silently dropped


def test_compose_briefing_end_to_end_without_hitting_real_api(monkeypatch, data_dir, tmp_path):
    # Force the summarize step to hit its ceiling-exceeded fallback so this
    # test never makes a real network call, while still exercising the full
    # compose_briefing() pipeline (calendar, repo status, activity, spend).
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.01")
    spend.record_spend(turn_id="prior", model="claude-sonnet-5", input_tokens=100_000, output_tokens=100_000)

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    text = briefing.compose_briefing()

    assert "CALENDAR" in text or "REPO STATUS" in text  # raw material preserved via the fallback
    assert "known-unknown" in text  # calendar degrades since there's no token

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'briefing'").fetchall()
    conn.close()
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload_json"])
    assert payload["text"] == text
