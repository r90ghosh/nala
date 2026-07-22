from nala import chokepoint, events
from nala.brain import RawIntent
from nala.cli import _memory_context_for_turn, process_turn, render_transcript


def test_process_turn_capture_task_via_fake_brain(data_dir, fake_backlog, make_fake_brain):
    brain = make_fake_brain(RawIntent(action_type="capture_task", args={
        "title": "write docs", "project": "life_os", "priority": "medium", "category": "chore",
    }))

    result = process_turn("add a task to write docs", brain=brain, session_id="sess-1")

    assert result.status == "done"
    assert brain.calls == 1
    assert len(fake_backlog.tasks) == 1


def test_transcript_renders_session_events(data_dir, fake_backlog, make_fake_brain):
    brain = make_fake_brain(RawIntent(action_type="report_status", args={}))
    process_turn("status please", brain=brain, session_id="sess-2")

    transcript = render_transcript()

    assert "sess-2" in transcript
    assert "utterance" in transcript


def test_memory_context_for_turn_is_none_when_graph_empty(data_dir):
    context = _memory_context_for_turn("hello", "t1", "s1")

    assert context is None


def test_memory_context_for_turn_is_none_when_recall_rejected(data_dir, monkeypatch):
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.00")  # ceiling already reached — memory_recall itself is rejected

    context = _memory_context_for_turn("hello", "t1", "s1")

    assert context is None


def test_memory_context_for_turn_surfaces_mentioned_node_and_its_observations(data_dir):
    chokepoint.execute_action(
        "memory_write",
        {
            "op": "add_observation", "kind": "person", "label": "Priya", "purpose_scope": "people",
            "fact": "loves ceramics", "source": "user_said", "source_ref": "prior chat",
        },
        turn_id="t0", session_id="s1",
    )

    context = _memory_context_for_turn("what does Priya like?", "t1", "s1")

    assert context is not None
    assert "Priya" in context
    assert "loves ceramics" in context


def test_process_turn_passes_memory_context_through_to_brain(data_dir):
    chokepoint.execute_action(
        "memory_write",
        {
            "op": "add_observation", "kind": "person", "label": "Priya", "purpose_scope": "people",
            "fact": "loves ceramics", "source": "user_said", "source_ref": "prior chat",
        },
        turn_id="t0", session_id="s1",
    )

    class RecordingBrain:
        def __init__(self):
            self.calls = 0
            self.received_memory_context = "unset"

        def decide(self, utterance, *, turn_id=None, session_id=None, memory_context=None):
            self.calls += 1
            self.received_memory_context = memory_context
            return RawIntent(action_type="report_status", args={})

    brain = RecordingBrain()
    process_turn("tell me about Priya", brain=brain, session_id="s1")

    assert brain.calls == 1
    assert brain.received_memory_context is not None
    assert "Priya" in brain.received_memory_context


def test_confirm_prefix_bypasses_brain(data_dir, fake_backlog, make_fake_brain):
    fake_backlog.tasks.append({
        "id": 9, "title": "old", "description": "", "project": "life_os",
        "priority": "low", "status": "backlog", "category": "chore",
    })
    first = chokepoint.execute_action("archive_task", {"task_id": 9}, turn_id="t1", session_id="s1")
    token = first.message.rsplit(" ", 1)[-1]

    brain = make_fake_brain(RawIntent(action_type="capture_task", args={}))  # must not be called
    result = process_turn(f"confirm {token}", brain=brain, session_id="s1")

    assert result.status == "done"
    assert brain.calls == 0
    assert events.last_session_id() == "s1"
