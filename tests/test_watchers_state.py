from nala.watchers import state


def test_watermark_roundtrip(data_dir):
    assert state.get_cursor("test-watcher") == {}
    state.set_cursor("test-watcher", {"foo": "bar"})
    assert state.get_cursor("test-watcher") == {"foo": "bar"}
    state.set_cursor("test-watcher", {"foo": "baz"})
    assert state.get_cursor("test-watcher") == {"foo": "baz"}


def test_watermarks_are_independent_per_watcher(data_dir):
    state.set_cursor("watcher-a", {"x": 1})
    state.set_cursor("watcher-b", {"y": 2})

    assert state.get_cursor("watcher-a") == {"x": 1}
    assert state.get_cursor("watcher-b") == {"y": 2}
