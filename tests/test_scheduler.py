"""Scheduler crash resilience. Watchers run on independent asyncio loops
with no built-in stopping condition, so these tests run the real loop for a
short bounded wall-clock window (fast intervals, no real network calls since
every watcher here returns zero signals — triage.run_pass short-circuits
before ever touching Ollama when there's nothing new to triage) and then
cancel it."""

import asyncio
import contextlib
import sqlite3

from nala import db, events, scheduler
from nala.watchers import base


class _CountingWatcher(base.Watcher):
    name = "counting"
    interval_seconds = 0.01

    def __init__(self):
        self.poll_count = 0

    def poll(self):
        self.poll_count += 1
        return []


class _AlwaysFailWatcher(base.Watcher):
    name = "alwaysfail"
    interval_seconds = 0.01

    def __init__(self):
        self.poll_count = 0

    def poll(self):
        self.poll_count += 1
        raise RuntimeError("this watcher always fails")


def test_one_watcher_failure_does_not_stop_others_across_multiple_ticks(data_dir):
    good = _CountingWatcher()
    bad = _AlwaysFailWatcher()

    async def scenario():
        good_task = asyncio.create_task(scheduler._watcher_loop(good, None))
        bad_task = asyncio.create_task(scheduler._watcher_loop(bad, None))
        await asyncio.sleep(0.3)
        good_task.cancel()
        bad_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await good_task
        with contextlib.suppress(asyncio.CancelledError):
            await bad_task

    asyncio.run(scenario())

    # The loop survives and continues on the next tick — both watchers kept
    # being invoked across many ticks, the bad one's repeated failures never
    # halted the good one's progress.
    assert good.poll_count >= 3
    assert bad.poll_count >= 3

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    assert len(rows) >= 1  # the bad watcher's failures were logged loudly, not swallowed


def test_log_event_raising_mid_signal_loop_is_contained(data_dir, monkeypatch):
    class _TwoSignalWatcher(base.Watcher):
        name = "twosignal"
        interval_seconds = 60

        def poll(self):
            return [
                base.Signal(source="test", kind="k1", title="t1", detail="d1", ref="r1"),
                base.Signal(source="test", kind="k2", title="t2", detail="d2", ref="r2"),
            ]

    real_log_event = events.log_event
    call_count = {"n": 0}

    def flaky_log_event(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise sqlite3.OperationalError("simulated disk full")
        return real_log_event(*args, **kwargs)

    monkeypatch.setattr(base.events, "log_event", flaky_log_event)

    result = base.run_poll(_TwoSignalWatcher(), session_id="s1", turn_id="t1")

    assert result == []  # contained — never propagated out of run_poll

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    # call 1 (signal 1's log) succeeded, call 2 (signal 2's log) raised, call 3
    # (loud_failure's own error-log attempt) succeeded — exactly one error row.
    assert len(rows) == 1


def test_run_forever_survives_a_watcher_task_dying_outright(data_dir):
    good = _CountingWatcher()

    class _DiesImmediately(base.Watcher):
        name = "dies"

        @property
        def interval_seconds(self):
            raise RuntimeError("misconfigured watcher — this escapes _watcher_loop's try/except")

        def poll(self):
            return []

    bad = _DiesImmediately()

    async def scenario():
        task = asyncio.create_task(scheduler.run_forever([good, bad], None))
        await asyncio.sleep(0.3)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            await task

    asyncio.run(scenario())

    # The good watcher's independent loop kept running even though the bad
    # one's task died outright.
    assert good.poll_count >= 1
