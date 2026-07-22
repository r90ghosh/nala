"""`python -m nala.scheduler` runs the watchers on one asyncio loop, each on
its own interval. Every poll's blocking I/O (git subprocess, Google API
calls, sqlite) runs via asyncio.to_thread so one slow watcher never stalls
the others — the same reason Phase A made the chokepoint guard
thread-independent: multiple watcher threads can end up dispatching through
execute_action concurrently once triage (M4c) lands."""

import asyncio
from pathlib import Path

from nala import events
from nala.watchers.base import Watcher, run_poll
from nala.watchers.calendar import CalendarWatcher
from nala.watchers.git import GitWatcher
from nala.watchers.gmail import GmailWatcher

SESSION_ID = "scheduler"


def default_watchers(data_dir: Path | None = None) -> list[Watcher]:
    return [
        GmailWatcher(data_dir=data_dir),
        CalendarWatcher(data_dir=data_dir),
        GitWatcher(data_dir=data_dir),
    ]


async def _watcher_loop(watcher: Watcher, data_dir: Path | None) -> None:
    while True:
        turn_id = events.new_id()
        await asyncio.to_thread(run_poll, watcher, session_id=SESSION_ID, turn_id=turn_id, data_dir=data_dir)
        await asyncio.sleep(watcher.interval_seconds)


async def run_forever(watchers: list[Watcher] | None = None, data_dir: Path | None = None) -> None:
    watchers = watchers if watchers is not None else default_watchers(data_dir)
    tasks = [asyncio.create_task(_watcher_loop(w, data_dir)) for w in watchers]
    await asyncio.gather(*tasks)


def main():
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
