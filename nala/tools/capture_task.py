"""Naive baseline: POST a task straight to the backlog. No validation, no
idempotency, no chokepoint — this is the deliberately naive control group."""

import httpx

from nala.config import get_backlog_url


def capture_task(title: str, project: str, priority: str, category: str) -> dict:
    payload = {
        "title": title,
        "project": project,
        "priority": priority,
        "category": category,
    }
    resp = httpx.post(f"{get_backlog_url()}/api/tasks", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()
