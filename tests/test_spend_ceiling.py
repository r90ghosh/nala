import pytest

from nala import chokepoint, spend
from nala.brain import Brain
from nala.spend import SpendCeilingExceeded


def test_brain_refuses_before_dispatch_over_ceiling(data_dir, monkeypatch):
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.01")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
    spend.record_spend(turn_id="prior", model="claude-sonnet-5", input_tokens=100_000, output_tokens=100_000)

    b = Brain()
    with pytest.raises(SpendCeilingExceeded):
        b.decide("do something", turn_id="t1", session_id="s1")


def test_chokepoint_refuses_over_ceiling(data_dir, fake_backlog, monkeypatch):
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.01")
    spend.record_spend(turn_id="prior", model="claude-sonnet-5", input_tokens=100_000, output_tokens=100_000)

    result = chokepoint.execute_action(
        "capture_task",
        {"title": "x", "project": "life_os", "priority": "low", "category": "chore"},
        turn_id="t1", session_id="s1",
    )

    assert result.status == "rejected"
    assert len(fake_backlog.tasks) == 0
