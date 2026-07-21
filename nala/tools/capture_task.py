"""POST a task to the backlog. Only ever invoked by the chokepoint."""

import httpx

from nala.config import get_backlog_url
from nala.tools import assert_in_chokepoint, register


@register("capture_task")
def capture_task(title: str, project: str, priority: str, category: str) -> dict:
    assert_in_chokepoint()
    payload = {
        "title": title,
        "project": project,
        "priority": priority,
        "category": category,
    }
    resp = httpx.post(f"{get_backlog_url()}/api/tasks", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()
