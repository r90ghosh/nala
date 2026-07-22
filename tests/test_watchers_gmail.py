from googleapiclient.errors import HttpError

from nala import state
from nala.watchers.gmail import GmailWatcher


class _Resp(dict):
    def __init__(self, status):
        super().__init__(status=status, reason="error")
        self.status = status
        self.reason = "error"


def _http_error(status):
    return HttpError(_Resp(status), b'{"error": {"message": "x"}}')


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


def test_expired_history_id_404_rebaselines_and_recovers(data_dir):
    # A stale watermark makes Gmail's history.list 404 forever; the watcher must
    # re-baseline to the current historyId and recover, not flood the feed.
    state.set_cursor("gmail", {"history_id": "100"})
    service = FakeGmailService(profile={"historyId": "999"})
    service.list = lambda **kwargs: (_ for _ in ()).throw(_http_error(404))
    watcher = GmailWatcher(service_factory=lambda: service)

    signals = watcher.poll()

    assert signals == []
    assert state.get_cursor("gmail") == {"history_id": "999"}


def test_message_get_404_skips_that_message_not_the_whole_poll(data_dir):
    # history references a message that's since been deleted; get() 404s on it.
    # The poll must skip it, still emit the good message, and advance the watermark
    # (otherwise the bad id poisons every future poll).
    state.set_cursor("gmail", {"history_id": "500"})
    history_resp = {
        "history": [{"messagesAdded": [{"message": {"id": "gone"}}, {"message": {"id": "m2"}}]}],
        "historyId": "700",
    }
    messages = {
        "m2": {
            "id": "m2", "labelIds": ["INBOX"], "snippet": "ok",
            "payload": {"headers": [{"name": "From", "value": "x@y.com"}, {"name": "Subject", "value": "real"}]},
        },
    }
    service = FakeGmailService(history_resp=history_resp, messages=messages)
    orig_get = service.get

    def get(userId, id, format, metadataHeaders):
        if id == "gone":
            raise _http_error(404)
        return orig_get(userId=userId, id=id, format=format, metadataHeaders=metadataHeaders)

    service.get = get
    watcher = GmailWatcher(service_factory=lambda: service)

    signals = watcher.poll()

    assert len(signals) == 1
    assert signals[0].title == "real"
    assert state.get_cursor("gmail") == {"history_id": "700"}


def test_non_404_http_error_propagates(data_dir):
    # A real error (e.g. 500) must NOT be swallowed as a re-baseline.
    state.set_cursor("gmail", {"history_id": "100"})
    service = FakeGmailService(profile={"historyId": "999"})
    service.list = lambda **kwargs: (_ for _ in ()).throw(_http_error(500))
    watcher = GmailWatcher(service_factory=lambda: service)

    try:
        watcher.poll()
        raised = False
    except HttpError:
        raised = True
    assert raised
    # watermark untouched on a genuine error
    assert state.get_cursor("gmail") == {"history_id": "100"}
