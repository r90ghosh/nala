from nala.watchers import state
from nala.watchers.gmail import GmailWatcher


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeGmailService:
    """Mimics the fluent googleapiclient interface for exactly the calls
    GmailWatcher makes: users().getProfile()/.history().list()/.messages().get()."""

    def __init__(self, profile=None, history_resp=None, messages=None):
        self.profile = profile or {}
        self.history_resp = history_resp or {"history": [], "historyId": "0"}
        self._messages = messages or {}

    def users(self):
        return self

    def getProfile(self, userId):
        return _Exec(self.profile)

    def history(self):
        return self

    def list(self, **kwargs):
        return _Exec(self.history_resp)

    def messages(self):
        return self

    def get(self, userId, id, format, metadataHeaders):
        return _Exec(self._messages[id])


def test_first_poll_establishes_baseline_no_signals(data_dir):
    service = FakeGmailService(profile={"historyId": "500"})
    watcher = GmailWatcher(service_factory=lambda: service)

    signals = watcher.poll()

    assert signals == []
    assert state.get_cursor("gmail") == {"history_id": "500"}


def test_second_poll_returns_new_messages_and_advances_watermark(data_dir):
    state.set_cursor("gmail", {"history_id": "500"})
    history_resp = {"history": [{"messagesAdded": [{"message": {"id": "m1"}}]}], "historyId": "600"}
    messages = {
        "m1": {
            "id": "m1",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "hey there",
            "payload": {"headers": [{"name": "From", "value": "a@b.com"}, {"name": "Subject", "value": "hello"}]},
        },
    }
    service = FakeGmailService(history_resp=history_resp, messages=messages)
    watcher = GmailWatcher(service_factory=lambda: service)

    signals = watcher.poll()

    assert len(signals) == 1
    assert signals[0].title == "hello"
    assert "a@b.com" in signals[0].detail
    assert signals[0].ref == "m1"
    assert state.get_cursor("gmail") == {"history_id": "600"}


def test_repoll_with_no_new_history_returns_no_duplicate_signals(data_dir):
    state.set_cursor("gmail", {"history_id": "600"})
    service = FakeGmailService(history_resp={"history": [], "historyId": "600"})
    watcher = GmailWatcher(service_factory=lambda: service)

    signals = watcher.poll()

    assert signals == []
