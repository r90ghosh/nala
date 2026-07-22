"""Typed-text REPL. M3: startup reconciliation, and a `confirm <token>`
utterance intercepted before the brain to complete an irreversible action
that's awaiting confirmation."""

import argparse
import json

from nala import chokepoint, events, purposes, reconciler
from nala.brain import Brain, BrainError
from nala.briefing import compose_briefing
from nala.errors import loud_failure
from nala.spend import SpendCeilingExceeded


def process_turn(utterance: str, *, brain: Brain, session_id: str, turn_id: str | None = None) -> chokepoint.ActionResult:
    turn_id = turn_id or events.new_id()
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


def render_pending() -> str:
    rows = chokepoint.list_processed_actions(limit=50)
    awaiting = [r for r in rows if r["status"] == "awaiting_confirm"]
    if not awaiting:
        return "nothing awaiting confirmation"

    lines = []
    for row in awaiting:
        token = row["idempotency_key"][:8]
        origin = row.get("origin", {"kind": "user"})
        lines.append(f"[{token}] {row['action_type']} {row['args_json']}")
        lines.append(f"  {chokepoint.format_origin_line(origin)}")
    return "\n".join(lines)


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


def _run_turn(utterance: str, *, brain: Brain, session_id: str) -> str:
    """Top-level catch-all around process_turn: whatever goes wrong, the
    session must survive it. process_turn already handles the known failure
    modes (BrainError, SpendCeilingExceeded) and returns a controlled
    ActionResult for those; this is the safety net for anything else."""
    turn_id = events.new_id()
    try:
        with loud_failure(session_id, turn_id, "process_turn"):
            result = process_turn(utterance, brain=brain, session_id=session_id, turn_id=turn_id)
    except Exception as exc:
        return f"turn failed unexpectedly: {exc}"
    return result.message


def _startup_reconcile(session_id: str) -> None:
    try:
        with loud_failure(session_id, "startup", "startup reconciliation"):
            reconciler.reconcile(session_id=session_id, turn_id="startup")
    except Exception as exc:
        print(f"warning: startup reconciliation failed: {exc}")


def main():
    purposes.load_all()  # malformed manifest is a loud startup failure, not a silent skip

    parser = argparse.ArgumentParser(prog="nala")
    parser.add_argument("--turn", help="run a single turn and exit")
    parser.add_argument("--briefing", action="store_true", help="compose and print the morning briefing")
    parser.add_argument("command", nargs="?", choices=["transcript", "pending"], default=None)
    args = parser.parse_args()

    if args.command == "transcript":
        print(render_transcript())
        return

    if args.command == "pending":
        print(render_pending())
        return

    if args.briefing:
        print(compose_briefing())
        return

    session_id = events.new_id()
    _startup_reconcile(session_id)
    brain = Brain()

    if args.turn:
        print(_run_turn(args.turn, brain=brain, session_id=session_id))
        return

    print("Nala (M3). Type 'exit' to quit, 'transcript' to view this session's log, 'pending' for awaiting confirmations.")
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
        if utterance.lower() == "pending":
            print(render_pending())
            continue
        print(_run_turn(utterance, brain=brain, session_id=session_id))


if __name__ == "__main__":
    main()
