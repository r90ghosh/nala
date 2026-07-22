"""Writes to the graph memory store. Only ever invoked by the chokepoint —
boundary validation (nala.validation.MemoryWriteIntent) has already checked
op-specific required fields; this just forwards to nala.memory."""

from nala import memory
from nala.tools import assert_valid_ticket, register


@register("memory_write")
def memory_write(
    op: str,
    kind: str | None = None,
    label: str | None = None,
    purpose_scope: str | None = None,
    src_node: str | None = None,
    rel: str | None = None,
    dst_node: str | None = None,
    node_id: str | None = None,
    fact: str | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    ticket=None,
) -> dict:
    assert_valid_ticket(ticket)

    if op == "upsert_node":
        return memory.upsert_node(kind, label, purpose_scope)
    if op == "add_edge":
        return memory.add_edge(src_node, rel, dst_node)
    if op == "add_observation":
        return memory.add_observation(
            fact, source, source_ref,
            node_id=node_id, kind=kind, label=label, purpose_scope=purpose_scope,
        )
    if op == "delete_node":
        return memory.delete_node(node_id)

    raise memory.MemoryError(f"unknown memory_write op '{op}'")
