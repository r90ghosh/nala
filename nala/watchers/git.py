"""Polls the tracked repos that actually exist on disk for newly-dirty
working trees and ahead/behind changes since the last poll."""

from pathlib import Path

from nala.config import PROJECTS, get_projects_root
from nala.tools.report_status import _git_info
from nala.watchers import state
from nala.watchers.base import Signal, Watcher


class GitWatcher(Watcher):
    name = "git"
    interval_seconds = 300

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir

    def poll(self) -> list[Signal]:
        root = get_projects_root()
        cursor = state.get_cursor(self.name, self.data_dir)
        last_known: dict = cursor.get("repos", {})

        signals: list[Signal] = []
        new_known: dict = dict(last_known)

        for name in PROJECTS:
            info = _git_info(root / name)
            if "error" in info:
                continue  # not a real git repo on disk — nothing to watch

            current = {
                "branch": info["branch"],
                "dirty": info["dirty"],
                "ahead": info["ahead"],
                "behind": info["behind"],
            }
            prev = last_known.get(name)

            if prev is None:
                # First time seeing this repo. Worth surfacing if it's
                # already dirty or diverged — that's new information to the
                # user even though it isn't a "change" in our own history.
                if current["dirty"] or current["ahead"] or current["behind"]:
                    signals.append(_repo_signal(name, current, "dirty_or_diverged"))
            elif current["dirty"] and not prev.get("dirty"):
                signals.append(_repo_signal(name, current, "newly_dirty"))
            elif current["ahead"] != prev.get("ahead") or current["behind"] != prev.get("behind"):
                signals.append(_repo_signal(name, current, "diverged"))

            new_known[name] = current

        state.set_cursor(self.name, {"repos": new_known}, self.data_dir)
        return signals


def _repo_signal(name: str, current: dict, kind: str) -> Signal:
    detail = (
        f"branch={current['branch']} dirty={current['dirty']} "
        f"ahead={current['ahead']} behind={current['behind']}"
    )
    return Signal(source="git", kind=kind, title=f"{name}: {kind.replace('_', ' ')}", detail=detail, ref=name)
