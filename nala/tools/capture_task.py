"""POST a task to the backlog. Only ever invoked by the chokepoint.

client_ref is embedded in the description as "[ref:<idempotency_key>]" so the
reconciler can match a stuck-pending row against the backlog's own record of
what actually landed."""

import httpx

from nala.config import get_backlog_url
from nala.tools import assert_valid_ticket, register


@register("capture_task")
def capture_task(title: str, project: str, priority: str, category: str, client_ref: str, ticket=None) -> dict:
    assert_valid_ticket(ticket)
    payload = {
        "title": title,
        "project": project,
        "priority": priority,
        "category": category,
        "description": f"[ref:{client_ref}]",
    }
    resp = httpx.post(f"{get_backlog_url()}/api/tasks", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()
