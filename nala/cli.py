"""Typed-text REPL. M3: startup reconciliation, and a `confirm <token>`
utterance intercepted before the brain to complete an irreversible action
that's awaiting confirmation."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from nala import chokepoint, events, purposes, reconciler
from nala.brain import Brain, BrainError
from nala.briefing import compose_briefing
from nala.errors import loud_failure
from nala.spend import SpendCeilingExceeded

MEMORY_CONTEXT_TOP_K = 8


def _memory_context_for_turn(utterance: str, turn_id: str, session_id: str) -> str | None:
    """Pulls a small, relevant slice of the memory graph before the brain
    call so chat can reference what it already knows without the user
    re-stating it — no embeddings in M5, just "mentioned in the utterance"
    first, then filled out by recency. Goes through the same memory_recall
    dispatch (and the same feed logging) as any other tool call. Returns
    None if memory is empty, unreachable, or nothing is worth surfacing —
    never blocks or degrades the turn itself."""
    result = chokepoint.execute_action("memory_recall", {}, turn_id=turn_id, session_id=session_id)
    if result.status != "done":
        return None

    nodes = result.data.get("nodes", [])
    if not nodes:
        return None

    lowered = utterance.lower()
    mentioned = [n for n in nodes if n["label"].lower() in lowered]
    mentioned_ids = {n["node_id"] for n in mentioned}
    recent = [n for n in nodes if n["node_id"] not in mentioned_ids]  # already recency-ordered by memory.query
    top = (mentioned + recent)[:MEMORY_CONTEXT_TOP_K]
    if not top:
        return None

    obs_by_node: dict[str, list[dict]] = {}
    for obs in result.data.get("observations", []):
        obs_by_node.setdefault(obs["node_id"], []).append(obs)

    lines = ["Known context from the personal memory graph (use it if relevant, otherwise ignore it):"]
    for n in top:
        facts = obs_by_node.get(n["node_id"], [])[:3]
        fact_str = "; ".join(f"{o['fact']} (source: {o['source']})" for o in facts) if facts else "(no observations recorded)"
        lines.append(f"- {n['label']} [{n['kind']}, {n['purpose_scope']}]: {fact_str}")
    return "\n".join(lines)


def process_turn(utterance: str, *, brain: Brain, session_id: str, turn_id: str | None = None) -> chokepoint.ActionResult:
    turn_id = turn_id or events.new_id()
    events.log_event(session_id, turn_id, "utterance", {"text": utterance})

    stripped = utterance.strip()
    if stripped.lower().startswith("confirm "):
        token = stripped.split(None, 1)[1].strip()
        return chokepoint.confirm_action(token, turn_id=turn_id, session_id=session_id)

    memory_context = _memory_context_for_turn(utterance, turn_id, session_id)

    try:
        intent = brain.decide(utterance, turn_id=turn_id, session_id=session_id, memory_context=memory_context)
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


def _speak(text: str) -> None:
    """Lazy voice import — only `--briefing --speak` needs the MLX/Kokoro
    stack loaded; every other CLI invocation shouldn't pay that import cost."""
    from nala import voice
    audio_bytes = voice.synthesize(text)
    tmp_path = Path(tempfile.mkstemp(suffix=".wav")[1])
    tmp_path.write_bytes(audio_bytes)
    try:
        subprocess.run(["afplay", str(tmp_path)], check=True)
    finally:
        tmp_path.unlink(missing_ok=True)


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
    parser.add_argument("--speak", action="store_true", help="with --briefing, also synthesize and play it aloud (afplay)")
    parser.add_argument("command", nargs="?", choices=["transcript", "pending"], default=None)
    args = parser.parse_args()

    if args.command == "transcript":
        print(render_transcript())
        return

    if args.command == "pending":
        print(render_pending())
        return

    if args.briefing:
        text = compose_briefing()
        print(text)
        if args.speak:
            _speak(text)
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
