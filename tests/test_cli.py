from nala import chokepoint, events
from nala.brain import RawIntent
from nala.cli import process_turn, render_transcript


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
