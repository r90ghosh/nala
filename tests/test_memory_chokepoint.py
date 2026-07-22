from nala import chokepoint, db, memory


def test_memory_recall_bypasses_idempotency_ledger(data_dir):
    memory.upsert_node("person", "Priya", "people")

    result = chokepoint.execute_action("memory_recall", {"kind": "person"}, turn_id="t1", session_id="s1")

    assert result.status == "done"
    assert len(result.data["nodes"]) == 1

    conn = db.connect()
    from nala.db import ensure_processed_actions
    ensure_processed_actions(conn)
    rows = conn.execute("SELECT * FROM processed_actions").fetchall()
    conn.close()
    assert rows == []  # pure read — never touches the ledger, like report_status


def test_memory_write_upsert_node_dispatches_and_lands_in_feed(data_dir):
    result = chokepoint.execute_action(
        "memory_write",
        {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "people"},
        turn_id="t1", session_id="s1",
    )

    assert result.status == "done"
    assert result.data["created"] is True

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'memory_write'").fetchall()
    conn.close()
    assert len(rows) == 1


def test_memory_write_add_observation_with_existing_node_id(data_dir):
    node = memory.upsert_node("person", "Priya", "people")

    result = chokepoint.execute_action(
        "memory_write",
        {"op": "add_observation", "node_id": node["node_id"], "fact": "likes ceramics", "source": "user_said", "source_ref": "turn-1"},
        turn_id="t2", session_id="s1",
    )

    assert result.status == "done"
    assert result.data["node_id"] == node["node_id"]


def test_memory_write_add_observation_find_or_creates(data_dir):
    result = chokepoint.execute_action(
        "memory_write",
        {
            "op": "add_observation", "kind": "person", "label": "Priya", "purpose_scope": "people",
            "fact": "likes ceramics", "source": "triage", "source_ref": "signal-1",
        },
        turn_id="t3", session_id="s1",
    )

    assert result.status == "done"
    recall = memory.query(label="Priya")
    assert len(recall["nodes"]) == 1
    assert len(recall["observations"]) == 1


def test_memory_write_add_edge(data_dir):
    a = memory.upsert_node("person", "Priya", "people")
    b = memory.upsert_node("thing", "ceramics", "relationships")

    result = chokepoint.execute_action(
        "memory_write",
        {"op": "add_edge", "src_node": a["node_id"], "rel": "likes", "dst_node": b["node_id"]},
        turn_id="t4", session_id="s1",
    )

    assert result.status == "done"


def test_memory_write_delete_node(data_dir):
    node = memory.upsert_node("person", "Priya", "people")

    result = chokepoint.execute_action(
        "memory_write", {"op": "delete_node", "node_id": node["node_id"]},
        turn_id="t5", session_id="s1",
    )

    assert result.status == "done"
    assert memory.query(label="Priya")["nodes"] == []


def test_memory_write_invalid_op_is_rejected_no_side_effect(data_dir):
    result = chokepoint.execute_action(
        "memory_write", {"op": "reticulate_splines", "node_id": "x"},
        turn_id="t6", session_id="s1",
    )

    assert result.status == "rejected"


def test_memory_write_upsert_node_missing_fields_is_rejected(data_dir):
    result = chokepoint.execute_action(
        "memory_write", {"op": "upsert_node", "kind": "person"},  # missing label, purpose_scope
        turn_id="t7", session_id="s1",
    )

    assert result.status == "rejected"


def test_memory_write_unknown_kind_rejected_with_suggestion(data_dir):
    result = chokepoint.execute_action(
        "memory_write",
        {"op": "upsert_node", "kind": "persoon", "label": "Priya", "purpose_scope": "people"},
        turn_id="t8", session_id="s1",
    )

    assert result.status == "rejected"
    assert "person" in result.message


def test_memory_write_unknown_purpose_scope_rejected(data_dir):
    result = chokepoint.execute_action(
        "memory_write",
        {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "not-a-real-purpose"},
        turn_id="t9", session_id="s1",
    )

    assert result.status == "rejected"


def test_memory_write_duplicate_turn_is_idempotent(data_dir):
    args = {"op": "upsert_node", "kind": "person", "label": "Priya", "purpose_scope": "people"}

    r1 = chokepoint.execute_action("memory_write", args, turn_id="same-turn", session_id="s1")
    r2 = chokepoint.execute_action("memory_write", args, turn_id="same-turn", session_id="s1")

    assert r1.status == "done"
    assert r2.status == "done"
    assert r1.data["node_id"] == r2.data["node_id"]

    conn = memory.connect()
    rows = conn.execute("SELECT * FROM nodes").fetchall()
    conn.close()
    assert len(rows) == 1  # never double-created
