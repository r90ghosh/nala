from nala import chokepoint


def test_archive_task_refused_without_confirm(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 5, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })

    result = chokepoint.execute_action("archive_task", {"task_id": 5}, turn_id="t1", session_id="s1")

    assert result.status == "awaiting_confirm"
    assert fake_backlog.tasks[0]["status"] == "backlog"  # unchanged, no side effect


def test_archive_task_succeeds_after_matching_confirm(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 6, "title": "old2", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })

    first = chokepoint.execute_action("archive_task", {"task_id": 6}, turn_id="t1", session_id="s1")
    assert first.status == "awaiting_confirm"
    token = first.message.rsplit(" ", 1)[-1]

    second = chokepoint.confirm_action(token, turn_id="t2", session_id="s1")

    assert second.status == "done"
    assert fake_backlog.tasks[0]["status"] == "archived"
