"""Stub, irreversible. Marks a task archived via the backlog's status
endpoint. Tagged irreversible in nala.validation — the chokepoint refuses to
dispatch this without a typed `confirm <token>`."""

import httpx

from nala.config import get_backlog_url
from nala.tools import assert_valid_ticket, register


@register("archive_task")
def archive_task(task_id: int, ticket=None) -> dict:
    assert_valid_ticket(ticket)
    resp = httpx.put(
        f"{get_backlog_url()}/api/tasks/{task_id}/status",
        json={"status": "archived"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
