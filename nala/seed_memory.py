"""`python -m nala.seed_memory` — seeds the user's real starter graph: the 7
tracked projects as project nodes, plus a single 'you' person node. Nothing
invented — no fake relationships, gifts, or other placeholder data; that's
for the graph to accumulate on its own via triage and chat. Safe to re-run:
upsert_node dedups on (kind, label, purpose_scope)."""

from nala import memory
from nala.validation import Project


def seed() -> list[dict]:
    results = [memory.upsert_node("person", "you", "people")]
    for project in Project:
        results.append(memory.upsert_node("project", project.value, "projects"))
    return results


def main() -> None:
    for r in seed():
        verb = "created" if r["created"] else "already existed"
        print(f"{verb}: {r['kind']} '{r['label']}' ({r['purpose_scope']})")


if __name__ == "__main__":
    main()
