"""Typed-text REPL. M1 adds the append-only event log: every utterance, LLM
request/response, tool call/result, and error is routed through nala.events.
Nothing may happen off-log from here on."""

import argparse
import json

from nala import events
from nala.brain import Brain
from nala.tools.capture_task import capture_task
from nala.tools.report_status import report_status


def dispatch(brain: Brain, utterance: str, session_id: str) -> str:
    turn_id = events.new_id()
    events.log_event(session_id, turn_id, "utterance", {"text": utterance})

    events.log_event(session_id, turn_id, "llm_request", {"utterance": utterance, "model": brain.model})
    try:
        tool_name, tool_input = brain.decide(utterance)
    except Exception as exc:
        events.log_event(
            session_id, turn_id, "error",
            {"context": "brain.decide", "exception": type(exc).__name__, "message": str(exc)},
            level="error",
        )
        return f"brain call failed: {exc}"
    events.log_event(session_id, turn_id, "llm_response", {"tool_name": tool_name, "tool_input": tool_input})

    if tool_name == "capture_task":
        events.log_event(session_id, turn_id, "tool_call", {"tool": "capture_task", "args": tool_input})
        try:
            task = capture_task(
                title=tool_input.get("title", ""),
                project=tool_input.get("project", ""),
                priority=tool_input.get("priority", "medium"),
                category=tool_input.get("category", "feature"),
            )
        except Exception as exc:
            events.log_event(
                session_id, turn_id, "error",
                {"context": "capture_task", "exception": type(exc).__name__, "message": str(exc)},
                level="error",
            )
            return f"capture_task failed: {exc}"
        events.log_event(session_id, turn_id, "tool_result", {"tool": "capture_task", "result": task})
        return f"captured task #{task['id']}: {task['title']}"

    if tool_name == "report_status":
        events.log_event(session_id, turn_id, "tool_call", {"tool": "report_status", "args": {}})
        try:
            rows = report_status()
        except Exception as exc:
            events.log_event(
                session_id, turn_id, "error",
                {"context": "report_status", "exception": type(exc).__name__, "message": str(exc)},
                level="error",
            )
            return f"report_status failed: {exc}"
        events.log_event(session_id, turn_id, "tool_result", {"tool": "report_status", "result": rows})
        lines = []
        for r in rows:
            if "error" in r:
                lines.append(f"{r['repo']}: {r['error']}")
                continue
            flags = "(dirty)" if r["dirty"] else ""
            lines.append(f"{r['repo']}: {r['branch']} {flags}".rstrip())
        return "\n".join(lines)

    events.log_event(session_id, turn_id, "error", {"context": "dispatch", "reason": "no tool selected"}, level="error")
    return "I couldn't figure out what to do with that."


def render_transcript() -> str:
    session_id = events.last_session_id()
    if session_id is None:
        return "no events recorded yet"
    rows = events.events_for_session(session_id)
    lines = [f"session {session_id}"]
    for row in rows:
        payload = json.loads(row["payload_json"])
        turn = row["turn_id"] or "-"
        lines.append(f"  [{row['ts']}] {row['type']:<12} ({row['level']}) turn={turn} {payload}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(prog="nala")
    parser.add_argument("--turn", help="run a single turn and exit")
    parser.add_argument("command", nargs="?", choices=["transcript"], default=None)
    args = parser.parse_args()

    if args.command == "transcript":
        print(render_transcript())
        return

    session_id = events.new_id()
    brain = Brain()

    if args.turn:
        print(dispatch(brain, args.turn, session_id))
        return

    print("Nala (M1). Type 'exit' to quit, 'transcript' to view this session's log.")
    while True:
        try:
            utterance = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if utterance.lower() in {"exit", "quit"}:
            break
        if not utterance:
            continue
        if utterance.lower() == "transcript":
            print(render_transcript())
            continue
        print(dispatch(brain, utterance, session_id))


if __name__ == "__main__":
    main()
