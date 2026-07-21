from nala import chokepoint, db


def test_duplicate_capture_task_turn_is_idempotent(data_dir, fake_backlog):
    args = {"title": "fix flaky test", "project": "life_os", "priority": "medium", "category": "bug"}

    r1 = chokepoint.execute_action("capture_task", args, turn_id="turn-abc", session_id="sess-1")
    r2 = chokepoint.execute_action("capture_task", args, turn_id="turn-abc", session_id="sess-1")

    assert r1.status == "done"
    assert r2.status == "done"
    assert r1.data["id"] == r2.data["id"]
    assert len(fake_backlog.tasks) == 1

    conn = db.connect()
    rows = conn.execute("SELECT * FROM processed_actions").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["status"] == "done"


def test_different_turns_are_not_deduped(data_dir, fake_backlog):
    args = {"title": "fix flaky test", "project": "life_os", "priority": "medium", "category": "bug"}

    chokepoint.execute_action("capture_task", args, turn_id="turn-1", session_id="sess-1")
    chokepoint.execute_action("capture_task", args, turn_id="turn-2", session_id="sess-1")

    assert len(fake_backlog.tasks) == 2
