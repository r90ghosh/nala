from nala import memory, seed_memory
from nala.validation import Project


def test_seed_creates_you_node_and_all_tracked_projects(data_dir):
    results = seed_memory.seed()

    assert len(results) == 1 + len(list(Project))
    assert all(r["created"] for r in results)

    you = memory.query(label="you", kind="person")
    assert len(you["nodes"]) == 1
    assert you["nodes"][0]["purpose_scope"] == "people"

    projects = memory.query(kind="project", purpose_scope="projects")
    assert {n["label"] for n in projects["nodes"]} == {p.value for p in Project}


def test_seed_is_idempotent_safe_to_rerun(data_dir):
    seed_memory.seed()
    results = seed_memory.seed()

    assert all(not r["created"] for r in results)  # second run finds everything already there

    all_nodes = memory.query()
    assert len(all_nodes["nodes"]) == 1 + len(list(Project))  # no duplicates
