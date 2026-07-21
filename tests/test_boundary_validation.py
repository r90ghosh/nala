from nala import chokepoint


def test_out_of_set_project_rejected_with_suggestion_no_post(data_dir, fake_backlog):
    result = chokepoint.execute_action(
        "capture_task",
        {"title": "x", "project": "last mile", "priority": "medium", "category": "chore"},
        turn_id="t1", session_id="s1",
    )

    assert result.status == "rejected"
    assert "last_mile" in result.message
    assert len(fake_backlog.tasks) == 0


def test_out_of_set_priority_rejected(data_dir, fake_backlog):
    result = chokepoint.execute_action(
        "capture_task",
        {"title": "x", "project": "life_os", "priority": "urgent", "category": "chore"},
        turn_id="t2", session_id="s1",
    )

    assert result.status == "rejected"
    assert len(fake_backlog.tasks) == 0
