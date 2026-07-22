from nala import db
from nala.watchers.base import Signal, Watcher, run_poll


class _BoomWatcher(Watcher):
    name = "boom"
    interval_seconds = 60

    def poll(self):
        raise RuntimeError("simulated watcher failure")


class _FixedWatcher(Watcher):
    name = "fixed"
    interval_seconds = 60

    def poll(self):
        return [Signal(source="test", kind="thing", title="T", detail="D", ref="r1")]


def test_watcher_failure_is_loud_not_a_crash(data_dir):
    signals = run_poll(_BoomWatcher(), session_id="s1", turn_id="t1")

    assert signals == []

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE level = 'error'").fetchall()
    conn.close()
    assert any(r["type"] == "error" for r in rows)


def test_signals_are_logged_as_signal_events(data_dir):
    signals = run_poll(_FixedWatcher(), session_id="s1", turn_id="t1")

    assert len(signals) == 1

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'signal'").fetchall()
    conn.close()
    assert len(rows) == 1
