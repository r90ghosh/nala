"""Shell out to git across the tracked repos. Only ever invoked by the
chokepoint."""

import subprocess
from pathlib import Path

from nala.config import PROJECTS, get_projects_root
from nala.tools import assert_valid_ticket, register


def _git_info(repo_path: Path) -> dict:
    name = repo_path.name
    if not (repo_path / ".git").exists():
        return {"repo": name, "error": "not a git repository"}

    branch = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()

    dirty = bool(
        subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    )

    ahead, behind = None, None
    upstream = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", f"{branch}@{{u}}"],
        capture_output=True, text=True, timeout=5,
    )
    if upstream.returncode == 0:
        counts = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--left-right", "--count", f"{branch}...{branch}@{{u}}"],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
        if len(counts) == 2:
            ahead, behind = int(counts[0]), int(counts[1])

    return {"repo": name, "branch": branch, "dirty": dirty, "ahead": ahead, "behind": behind}


@register("report_status")
def report_status(ticket=None) -> list[dict]:
    assert_valid_ticket(ticket)
    root = get_projects_root()
    return [_git_info(root / name) for name in PROJECTS]
