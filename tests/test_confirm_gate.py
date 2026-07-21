from nala import chokepoint, db


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


def test_confirm_with_wildcard_token_is_rejected_not_executed(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 7, "title": "old3", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    first = chokepoint.execute_action("archive_task", {"task_id": 7}, turn_id="t1", session_id="s1")
    assert first.status == "awaiting_confirm"

    # A raw SQL LIKE wildcard must never be treated as a valid token.
    result = chokepoint.confirm_action("%", turn_id="t2", session_id="s1")

    assert result.status == "rejected"
    assert fake_backlog.tasks[0]["status"] == "backlog"  # still unarchived — no side effect ran


def test_confirm_with_underscore_wildcard_token_is_rejected(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 8, "title": "old4", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    chokepoint.execute_action("archive_task", {"task_id": 8}, turn_id="t1", session_id="s1")

    result = chokepoint.confirm_action("_", turn_id="t2", session_id="s1")

    assert result.status == "rejected"
    assert fake_backlog.tasks[0]["status"] == "backlog"


def test_confirm_with_ambiguous_prefix_is_rejected(data_dir, fake_backlog):
    # Directly seed two awaiting_confirm rows that share a prefix — real
    # sha256 keys colliding on a short prefix is astronomically unlikely
    # naturally, so we construct the collision to exercise the ambiguity path.
    conn = db.connect()
    from nala.db import ensure_processed_actions
    ensure_processed_actions(conn)
    for suffix in ("1111", "2222"):
        conn.execute(
            "INSERT INTO processed_actions "
            "(idempotency_key, turn_id, action_type, reversibility, args_json, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (f"aaaa{suffix}", "t1", "archive_task", "irreversible", '{"task_id": 1}', "awaiting_confirm", "2026-01-01T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()

    result = chokepoint.confirm_action("aaaa", turn_id="t2", session_id="s1")

    assert result.status == "rejected"
    assert "ambiguous" in result.message.lower()


def test_confirm_with_full_key_still_works(data_dir, fake_backlog):
    fake_backlog.tasks.append({
        "id": 9, "title": "old5", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    first = chokepoint.execute_action("archive_task", {"task_id": 9}, turn_id="t1", session_id="s1")
    assert first.status == "awaiting_confirm"

    conn = db.connect()
    row = conn.execute("SELECT idempotency_key FROM processed_actions WHERE status='awaiting_confirm'").fetchone()
    conn.close()
    full_key = row["idempotency_key"]

    second = chokepoint.confirm_action(full_key, turn_id="t2", session_id="s1")

    assert second.status == "done"
    assert fake_backlog.tasks[0]["status"] == "archived"
