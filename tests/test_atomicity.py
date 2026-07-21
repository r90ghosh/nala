import pytest

from nala import chokepoint, reconciler


class SimulatedCrash(Exception):
    pass


def test_crash_before_post_resolves_to_failed(data_dir, fake_backlog, monkeypatch):
    def crash_hook(checkpoint):
        if checkpoint == "after_pending_commit":
            raise SimulatedCrash()

    monkeypatch.setattr(chokepoint, "_crash_hook", crash_hook)

    with pytest.raises(SimulatedCrash):
        chokepoint.execute_action(
            "capture_task",
            {"title": "t1", "project": "life_os", "priority": "low", "category": "chore"},
            turn_id="turn-crash-1",
            session_id="s",
        )

    monkeypatch.setattr(chokepoint, "_crash_hook", None)

    assert len(fake_backlog.tasks) == 0  # crashed before the POST ever happened
    assert reconciler.in_doubt_count() == 1  # in-doubt until reconciled

    result = reconciler.reconcile()
    assert result["resolved_failed"] == 1
    assert result["resolved_done"] == 0
    assert reconciler.in_doubt_count() == 0


def test_crash_after_post_resolves_to_done(data_dir, fake_backlog, monkeypatch):
    def crash_hook(checkpoint):
        if checkpoint == "after_side_effect":
            raise SimulatedCrash()

    monkeypatch.setattr(chokepoint, "_crash_hook", crash_hook)

    with pytest.raises(SimulatedCrash):
        chokepoint.execute_action(
            "capture_task",
            {"title": "t2", "project": "life_os", "priority": "low", "category": "chore"},
            turn_id="turn-crash-2",
            session_id="s",
        )

    monkeypatch.setattr(chokepoint, "_crash_hook", None)

    assert len(fake_backlog.tasks) == 1  # the side effect landed before the "crash"
    assert reconciler.in_doubt_count() == 1

    result = reconciler.reconcile()
    assert result["resolved_done"] == 1
    assert result["resolved_failed"] == 0
    assert reconciler.in_doubt_count() == 0
