from nala.watchers.calendar import CalendarWatcher


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeCalendarService:
    def __init__(self, events_resp):
        self.events_resp = events_resp

    def events(self):
        return self

    def list(self, **kwargs):
        return _Exec(self.events_resp)


def test_first_poll_signals_all_upcoming_events(data_dir):
    resp = {
        "items": [
            {"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-07-22T10:00:00Z"}},
            {"id": "e2", "summary": "Dentist", "start": {"date": "2026-07-23"}},
        ],
    }
    watcher = CalendarWatcher(service_factory=lambda: FakeCalendarService(resp))

    signals = watcher.poll()

    assert {s.ref for s in signals} == {"e1", "e2"}
    assert all(s.kind == "upcoming_event" for s in signals)


def test_repoll_same_events_no_duplicate_signals(data_dir):
    resp = {"items": [{"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-07-22T10:00:00Z"}}]}
    watcher = CalendarWatcher(service_factory=lambda: FakeCalendarService(resp))

    watcher.poll()
    signals = watcher.poll()

    assert signals == []


def test_event_time_change_resignals_as_event_changed(data_dir):
    service = FakeCalendarService({"items": [{"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-07-22T10:00:00Z"}}]})
    watcher = CalendarWatcher(service_factory=lambda: service)
    watcher.poll()

    service.events_resp = {"items": [{"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-07-22T11:00:00Z"}}]}
    signals = watcher.poll()

    assert len(signals) == 1
    assert signals[0].kind == "event_changed"
