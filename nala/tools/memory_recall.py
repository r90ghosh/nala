"""Reads from the graph memory store. Only ever invoked by the chokepoint —
a pure read, so it (like report_status) bypasses the idempotency ledger."""

from nala import memory
from nala.tools import assert_valid_ticket, register


@register("memory_recall")
def memory_recall(
    label: str | None = None,
    kind: str | None = None,
    purpose_scope: str | None = None,
    ticket=None,
) -> dict:
    assert_valid_ticket(ticket)
    return memory.query(label=label, kind=kind, purpose_scope=purpose_scope)
