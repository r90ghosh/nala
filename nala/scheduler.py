"""`python -m nala.scheduler` runs the watchers on one asyncio loop, each on
its own interval, with a triage pass after every watcher poll. Every poll's
blocking I/O (git subprocess, Google API calls, Ollama call, sqlite) runs via
asyncio.to_thread so one slow watcher never stalls the others — the same
reason Phase A made the chokepoint guard thread-independent: multiple
watcher threads end up dispatching proposals through execute_action
concurrently once triage is in the loop.

Three layers keep one watcher's failure from taking down the whole process:
run_poll/triage.run_pass already degrade gracefully on their own expected
failure modes; _watcher_loop's per-iteration try/except is the backstop for
anything that still escapes that (defense in depth, not the primary path);
run_forever's return_exceptions=True means even a watcher task dying outright
(a BaseException, not a normal Exception) doesn't take the other watchers'
tasks down with it."""

import asyncio
import sys
from pathlib import Path

from nala import events, triage
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
        try:
            await asyncio.to_thread(run_poll, watcher, session_id=SESSION_ID, turn_id=turn_id, data_dir=data_dir)
            await asyncio.to_thread(triage.run_pass, turn_id=turn_id, data_dir=data_dir)
        except Exception as exc:
            try:
                events.log_event(
                    SESSION_ID, turn_id, "error",
                    {"context": f"{watcher.name} watcher loop", "exception": type(exc).__name__, "message": str(exc)},
                    level="error", data_dir=data_dir,
                )
            except Exception:
                # Logging itself failed (e.g. the disk is actually full) —
                # this is the last-resort fallback, not the primary path.
                print(f"CRITICAL: {watcher.name} watcher loop failed AND could not log it: {exc}", file=sys.stderr)
        await asyncio.sleep(watcher.interval_seconds)


async def run_forever(watchers: list[Watcher] | None = None, data_dir: Path | None = None) -> None:
    watchers = watchers if watchers is not None else default_watchers(data_dir)
    tasks = [asyncio.create_task(_watcher_loop(w, data_dir)) for w in watchers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for watcher, result in zip(watchers, results):
        if isinstance(result, BaseException):
            events.log_event(
                SESSION_ID, "scheduler-fatal", "error",
                {"context": f"{watcher.name} watcher task died", "exception": type(result).__name__, "message": str(result)},
                level="error", data_dir=data_dir,
            )


def main():
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
