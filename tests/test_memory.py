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


def test_upsert_node_concurrent_calls_produce_exactly_one_node(data_dir):
    # serve + scheduler + cli are genuinely separate long-running processes
    # hitting an ALREADY-INITIALIZED ~/.nala/memory.db — this simulates that
    # steady-state race with real OS threads, each opening its own
    # connection (as upsert_node always does). Pre-warming the schema below
    # matters: racing 10 threads through schema creation on a brand-new file
    # is a much harsher (and unrealistic) scenario than production ever
    # hits, and can occasionally exceed even a 5s busy_timeout on a loaded
    # test machine — not what this test is trying to prove.
    import threading

    memory.connect(data_dir).close()

    results = []
    errors = []

    def worker():
        try:
            results.append(memory.upsert_node("person", "Priya", "people"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 10
    assert len({r["node_id"] for r in results}) == 1  # every caller converged on the same single node
    assert sum(1 for r in results if r["created"]) == 1  # exactly one caller actually created it

    conn = memory.connect()
    rows = conn.execute(
        "SELECT * FROM nodes WHERE kind='person' AND label='Priya' AND purpose_scope='people'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_dedupe_existing_duplicate_nodes_merges_onto_survivor(data_dir):
    # Simulates a ~/.nala/memory.db from before this fix, where the old
    # SELECT-then-INSERT race already produced genuine duplicate nodes —
    # ensure_schema must clean these up before it can even create the new
    # unique index (which would otherwise fail outright on the duplicates).
    conn = memory.connect()
    conn.execute("DROP INDEX IF EXISTS idx_nodes_kind_label_scope")

    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO nodes (node_id, kind, label, purpose_scope, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("survivor", "person", "Priya", "people", now, now),
    )
    conn.execute(
        "INSERT INTO nodes (node_id, kind, label, purpose_scope, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("loser", "person", "Priya", "people", now, now),
    )
    conn.execute(
        "INSERT INTO observations (obs_id, node_id, fact, source, source_ref, observed_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("obs1", "loser", "loves ceramics", "user_said", "x", now, now),
    )
    conn.commit()
    conn.close()

    # Any later connect() re-runs ensure_schema, which must dedupe before
    # it can successfully (re-)create the unique index.
    conn2 = memory.connect()
    node_rows = conn2.execute("SELECT * FROM nodes WHERE label = 'Priya'").fetchall()
    obs_rows = conn2.execute("SELECT * FROM observations").fetchall()
    conn2.close()

    assert len(node_rows) == 1  # merged down to a single node
    assert obs_rows[0]["node_id"] == node_rows[0]["node_id"]  # the observation followed onto whichever node survived


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
