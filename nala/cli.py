"""Typed-text REPL. M3: startup reconciliation, and a `confirm <token>`
utterance intercepted before the brain to complete an irreversible action
that's awaiting confirmation."""

import argparse
import json

from nala import chokepoint, events, reconciler
from nala.brain import Brain, BrainError
from nala.errors import loud_failure
from nala.spend import SpendCeilingExceeded


def process_turn(utterance: str, *, brain: Brain, session_id: str) -> chokepoint.ActionResult:
    turn_id = events.new_id()
    events.log_event(session_id, turn_id, "utterance", {"text": utterance})

    stripped = utterance.strip()
    if stripped.lower().startswith("confirm "):
        token = stripped.split(None, 1)[1].strip()
        return chokepoint.confirm_action(token, turn_id=turn_id, session_id=session_id)

    try:
        intent = brain.decide(utterance, turn_id=turn_id, session_id=session_id)
    except BrainError as exc:
        events.log_event(session_id, turn_id, "rejected", {"reason": str(exc)}, level="error")
        return chokepoint.ActionResult(status="rejected", message=f"couldn't understand that: {exc}")
    except SpendCeilingExceeded as exc:
        events.log_event(session_id, turn_id, "rejected", {"reason": str(exc)}, level="error")
        return chokepoint.ActionResult(status="rejected", message=f"refused: {exc}")

    return chokepoint.execute_action(intent.action_type, intent.args, turn_id=turn_id, session_id=session_id)


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


def _startup_reconcile(session_id: str) -> None:
    try:
        with loud_failure(session_id, "startup", "startup reconciliation"):
            reconciler.reconcile(session_id=session_id, turn_id="startup")
    except Exception as exc:
        print(f"warning: startup reconciliation failed: {exc}")


def main():
    parser = argparse.ArgumentParser(prog="nala")
    parser.add_argument("--turn", help="run a single turn and exit")
    parser.add_argument("command", nargs="?", choices=["transcript"], default=None)
    args = parser.parse_args()

    if args.command == "transcript":
        print(render_transcript())
        return

    session_id = events.new_id()
    _startup_reconcile(session_id)
    brain = Brain()

    if args.turn:
        result = process_turn(args.turn, brain=brain, session_id=session_id)
        print(result.message)
        return

    print("Nala (M3). Type 'exit' to quit, 'transcript' to view this session's log.")
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
        result = process_turn(utterance, brain=brain, session_id=session_id)
        print(result.message)


if __name__ == "__main__":
    main()
