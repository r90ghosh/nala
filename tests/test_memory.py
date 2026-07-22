import pytest

from nala import memory


def test_upsert_node_creates_then_updates_not_duplicates(data_dir):
    first = memory.upsert_node("person", "Priya", "people")
    assert first["created"] is True

    second = memory.upsert_node("person", "Priya", "people")
    assert second["created"] is False
    assert second["node_id"] == first["node_id"]

    conn = memory.connect()
    rows = conn.execute("SELECT * FROM nodes").fetchall()
    conn.close()
    assert len(rows) == 1


def test_upsert_node_rejects_unknown_kind(data_dir):
    with pytest.raises(memory.MemoryError):
        memory.upsert_node("alien", "X", "people")


def test_add_edge_requires_both_nodes_to_exist(data_dir):
    a = memory.upsert_node("person", "Priya", "people")
    with pytest.raises(memory.MemoryError):
        memory.add_edge(a["node_id"], "likes", "nonexistent-node-id")


def test_add_edge_is_idempotent_on_duplicate(data_dir):
    a = memory.upsert_node("person", "Priya", "people")
    b = memory.upsert_node("thing", "ceramics", "relationships")
    memory.add_edge(a["node_id"], "likes", b["node_id"])
    memory.add_edge(a["node_id"], "likes", b["node_id"])

    conn = memory.connect()
    rows = conn.execute("SELECT * FROM edges").fetchall()
    conn.close()
    assert len(rows) == 1


def test_add_observation_without_source_raises(data_dir):
    node = memory.upsert_node("person", "Priya", "people")
    with pytest.raises(memory.MemoryError):
        memory.add_observation("likes ceramics", "", "event-123", node_id=node["node_id"])


def test_add_observation_without_source_ref_raises(data_dir):
    node = memory.upsert_node("person", "Priya", "people")
    with pytest.raises(memory.MemoryError):
        memory.add_observation("likes ceramics", "user_said", "", node_id=node["node_id"])


def test_add_observation_with_unknown_source_raises(data_dir):
    node = memory.upsert_node("person", "Priya", "people")
    with pytest.raises(memory.MemoryError):
        memory.add_observation("likes ceramics", "carrier_pigeon", "ref-1", node_id=node["node_id"])


def test_add_observation_against_existing_node_id(data_dir):
    node = memory.upsert_node("person", "Priya", "people")
    obs = memory.add_observation("likes ceramics", "user_said", "turn-1", node_id=node["node_id"])
    assert obs["node_id"] == node["node_id"]
    assert obs["source"] == "user_said"
    assert obs["source_ref"] == "turn-1"


def test_add_observation_find_or_creates_node(data_dir):
    obs = memory.add_observation(
        "likes ceramics", "triage", "signal-42",
        kind="person", label="Priya", purpose_scope="people",
    )
    conn = memory.connect()
    nodes = conn.execute("SELECT * FROM nodes WHERE label = 'Priya'").fetchall()
    conn.close()
    assert len(nodes) == 1
    assert obs["node_id"] == nodes[0]["node_id"]


def test_add_observation_requires_node_id_or_kind_label_scope(data_dir):
    with pytest.raises(memory.MemoryError):
        memory.add_observation("likes ceramics", "user_said", "turn-1")


def test_delete_node_cascades_edges_and_observations(data_dir):
    a = memory.upsert_node("person", "Priya", "people")
    b = memory.upsert_node("thing", "ceramics", "relationships")
    memory.add_edge(a["node_id"], "likes", b["node_id"])
    memory.add_observation("likes ceramics", "user_said", "turn-1", node_id=a["node_id"])

    memory.delete_node(a["node_id"])

    conn = memory.connect()
    nodes = conn.execute("SELECT * FROM nodes WHERE node_id = ?", (a["node_id"],)).fetchall()
    edges = conn.execute("SELECT * FROM edges").fetchall()
    obs = conn.execute("SELECT * FROM observations").fetchall()
    conn.close()
    assert nodes == []
    assert edges == []
    assert obs == []


def test_delete_node_unknown_id_raises(data_dir):
    with pytest.raises(memory.MemoryError):
        memory.delete_node("does-not-exist")


def test_query_filters_by_kind_and_purpose_and_returns_edges_observations(data_dir):
    priya = memory.upsert_node("person", "Priya", "people")
    ceramics = memory.upsert_node("thing", "ceramics", "relationships")
    memory.add_edge(priya["node_id"], "likes", ceramics["node_id"])
    memory.add_observation("likes ceramics", "user_said", "turn-1", node_id=priya["node_id"])

    result = memory.query(kind="person")
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["label"] == "Priya"
    assert len(result["edges"]) == 1
    assert len(result["observations"]) == 1

    result_scoped = memory.query(purpose_scope="relationships")
    assert len(result_scoped["nodes"]) == 1
    assert result_scoped["nodes"][0]["label"] == "ceramics"


def test_query_with_no_matches_returns_empty_shape(data_dir):
    result = memory.query(label="nobody-like-this")
    assert result == {"nodes": [], "edges": [], "observations": []}
