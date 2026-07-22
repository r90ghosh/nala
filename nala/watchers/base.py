"""Base Watcher contract + the sanctioned way to run one.

run_poll() is the only way a watcher's poll() should ever be invoked outside
a test: it wraps the call in loud_failure so an exception (missing Google
token, network error, git subprocess failure, ...) becomes a level='error'
event and a degraded (empty) result — never a crash, never silent. Signals a
watcher actually returns are logged as events rows type='signal'."""

from dataclasses import dataclass
from pathlib import Path

from nala import events
from nala.errors import loud_failure


@dataclass
class Signal:
    source: str  # e.g. "gmail", "calendar", "git"
    kind: str    # e.g. "new_message", "upcoming_event", "newly_dirty"
    title: str
    detail: str
    ref: str     # stable identifier for this item (message id, event id, repo name)


class Watcher:
    name: str = ""
    interval_seconds: int = 300

    def poll(self) -> list[Signal]:
        raise NotImplementedError


def run_poll(watcher: Watcher, *, session_id: str, turn_id: str, data_dir: Path | None = None) -> list[Signal]:
    try:
        with loud_failure(session_id, turn_id, f"{watcher.name} watcher poll", data_dir):
            signals = watcher.poll()
    except Exception:
        return []

    for signal in signals:
        events.log_event(
            session_id, turn_id, "signal",
            {"source": signal.source, "kind": signal.kind, "title": signal.title, "detail": signal.detail, "ref": signal.ref},
            data_dir=data_dir,
        )
    return signals
