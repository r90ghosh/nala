"""Consumes un-triaged signal events (nala.state watermark) and classifies
each with the local model (llama3.2:3b via Ollama's OpenAI-compatible
/chat/completions) into ignore | remember | propose, AND assigns a purpose
(one of the 8 from PLAN.md, or None if it doesn't clearly fit — never
guessed into whichever purpose happens to be most permissive).

Two distinct failure modes, handled differently:
- Ollama itself is unreachable: a batch-level failure. Loud (logged,
  level='error'), and the whole pass stops there without advancing the
  watermark past this or any later signal — everything is retried next pass.
- A single signal's model output is malformed or out-of-set: loud reject
  for that signal specifically (logged, level='error'), but the watermark
  DOES advance past it — retrying the exact same garbage forever helps no
  one, and other signals in the same batch are unaffected.

'propose' routes a capture_task through chokepoint.execute_action(...,
purpose=purpose); 'remember' (which used to be a no-op label) now routes a
memory_write the same way. Since M5, purpose — not a blanket force_confirm
— is what gates a proactive write: read_only purposes get rejected loudly,
notify_only lands as a dismissible 'notified' row with no side effect,
act_confirm lands as 'awaiting_confirm'. Boundary validation of the
proposed args is chokepoint's job, not re-implemented here."""

import json
from pathlib import Path

import httpx

from nala import chokepoint, db, events, spend, state
from nala.config import get_ollama_url
from nala.errors import loud_failure
from nala.routing import TRIAGE_MODEL

MODEL = TRIAGE_MODEL
SESSION_ID = "triage"
WATERMARK_NAME = "triage"

VALID_CLASSIFICATIONS = {"ignore", "remember", "propose"}
VALID_PURPOSES = {"projects", "finance", "baby", "relationships", "home", "news", "interests", "purchase"}
VALID_NODE_KINDS = {"person", "project", "preference", "event", "thing", "place"}

# execute_action treats purpose=None as "not a proactive call, skip risk
# gating entirely" (the direct-user-turn case). Every triage dispatch IS
# proactive, so an unassigned purpose must still pass *something* non-None —
# any string that isn't a real purpose name falls back to notify_only in
# chokepoint's gating, which is exactly the conservative behavior we want
# for "the model didn't confidently assign a purpose."
UNKNOWN_PURPOSE_SENTINEL = "unknown"

PURPOSE_DESCRIPTIONS = {
    "projects": "software project work, repo activity, dev tasks",
    "finance": "money, bills, subscriptions, spending",
    "baby": "childcare, pregnancy, parenting",
    "relationships": "friends, family, partner, social life",
    "home": "household, maintenance, chores",
    "news": "current events, articles",
    "interests": "hobbies, personal interests",
    "purchase": "shopping, orders, deliveries",
}


class TriageError(Exception):
    """The model's output for one signal couldn't be used — malformed JSON,
    missing fields, or an out-of-set classification. Distinct from Ollama
    being unreachable, which is a batch-level failure."""


def _build_prompt(signal_payload: dict) -> str:
    purposes_list = "\n".join(f"- {name}: {desc}" for name, desc in PURPOSE_DESCRIPTIONS.items())
    return (
        "You triage incoming signals for a personal proactive assistant. Classify the "
        "signal as exactly one of: ignore, remember, propose.\n"
        "- ignore: not worth remembering or acting on.\n"
        "- remember: worth keeping as a fact about a person/project/preference/event/thing/place.\n"
        "- propose: worth proposing a concrete task capture.\n\n"
        "ALSO assign the signal to exactly one purpose from this list, or null if none clearly "
        "fits — never guess if you're not confident:\n"
        f"{purposes_list}\n\n"
        f"Signal: {json.dumps(signal_payload)}\n\n"
        "Respond with ONLY a JSON object, no other text:\n"
        '{"classification": "ignore|remember|propose", "purpose": "<one of the 8 above> or null", '
        '"reason": "one line", '
        '"capture_task": {"title": "...", "project": "...", "priority": "...", "category": "..."} or null, '
        '"memory_write": {"kind": "person|project|preference|event|thing|place", "label": "...", "fact": "..."} or null}'
    )


def _classify(signal_payload: dict, turn_id: str, data_dir: Path | None) -> dict:
    """One Ollama call. Raises TriageError for malformed/invalid output.
    httpx/connection errors propagate as-is — the caller treats those as
    'Ollama unreachable', a different failure mode entirely."""
    resp = httpx.post(
        f"{get_ollama_url()}/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": _build_prompt(signal_payload)}],
            "response_format": {"type": "json_object"},
            "stream": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    spend.record_spend(
        turn_id=turn_id, model=MODEL,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        data_dir=data_dir,
    )

    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise TriageError(f"malformed model output: {exc}") from exc

    if not isinstance(parsed, dict) or parsed.get("classification") not in VALID_CLASSIFICATIONS:
        raise TriageError(f"unknown classification {parsed.get('classification') if isinstance(parsed, dict) else parsed!r}")

    # An out-of-set (or hallucinated) purpose is never guessed into a real
    # one — treated as unknown, which execute_action's risk gating then
    # treats as notify_only (the conservative default), same as if the
    # model had said null itself.
    if parsed.get("purpose") not in VALID_PURPOSES:
        parsed["purpose"] = None

    return parsed


def _fetch_untriaged_signals(data_dir: Path | None) -> list[dict]:
    cursor = state.get_cursor(WATERMARK_NAME, data_dir)
    last_id = cursor.get("last_event_id", 0)

    conn = db.connect(data_dir)
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE type = 'signal' AND id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _dispatch_propose(row: dict, result: dict, purpose: str | None, turn_id: str, data_dir: Path | None, counts: dict) -> None:
    proposal = result.get("capture_task")
    if not isinstance(proposal, dict):
        events.log_event(
            SESSION_ID, turn_id, "rejected",
            {"signal_event_id": row["id"], "reason": "propose classification missing valid capture_task args"},
            level="error", data_dir=data_dir,
        )
        return

    action_result = chokepoint.execute_action(
        "capture_task", proposal,
        turn_id=turn_id, session_id=SESSION_ID, data_dir=data_dir,
        purpose=purpose or UNKNOWN_PURPOSE_SENTINEL,
    )
    counts["proposed"] += 1
    events.log_event(
        SESSION_ID, turn_id, "triage",
        {"signal_event_id": row["id"], "proposal_status": action_result.status, "proposal_message": action_result.message},
        data_dir=data_dir,
    )


def _dispatch_remember(row: dict, result: dict, purpose: str | None, turn_id: str, data_dir: Path | None, counts: dict) -> None:
    mem = result.get("memory_write")
    if not (isinstance(mem, dict) and mem.get("kind") in VALID_NODE_KINDS and mem.get("label") and mem.get("fact")):
        events.log_event(
            SESSION_ID, turn_id, "rejected",
            {"signal_event_id": row["id"], "reason": "remember classification missing valid memory_write args"},
            level="error", data_dir=data_dir,
        )
        return

    # Persons live in the shared 'people' scope regardless of which purpose
    # observed them; everything else needs a determinable purpose to know
    # where in the graph it belongs.
    purpose_scope = "people" if mem["kind"] == "person" else purpose
    if purpose_scope is None:
        events.log_event(
            SESSION_ID, turn_id, "rejected",
            {"signal_event_id": row["id"], "reason": "remember proposal has no determinable purpose_scope (unknown purpose, non-person entity)"},
            level="error", data_dir=data_dir,
        )
        return

    memory_args = {
        "op": "add_observation",
        "kind": mem["kind"], "label": mem["label"], "purpose_scope": purpose_scope,
        "fact": mem["fact"], "source": "triage", "source_ref": str(row["id"]),
    }
    action_result = chokepoint.execute_action(
        "memory_write", memory_args,
        turn_id=turn_id, session_id=SESSION_ID, data_dir=data_dir,
        purpose=purpose or UNKNOWN_PURPOSE_SENTINEL,
    )
    counts["proposed"] += 1
    events.log_event(
        SESSION_ID, turn_id, "triage",
        {"signal_event_id": row["id"], "proposal_status": action_result.status, "proposal_message": action_result.message},
        data_dir=data_dir,
    )


def run_triage_pass(data_dir: Path | None = None) -> dict:
    signals = _fetch_untriaged_signals(data_dir)
    if not signals:
        return {"triaged": 0, "proposed": 0, "rejected": 0}

    counts = {"triaged": 0, "proposed": 0, "rejected": 0}

    for row in signals:
        turn_id = f"triage-{row['id']}"
        payload = json.loads(row["payload_json"])

        try:
            result = _classify(payload, turn_id, data_dir)
        except TriageError as exc:
            events.log_event(
                SESSION_ID, turn_id, "triage",
                {"signal_event_id": row["id"], "rejected": True, "reason": str(exc)},
                level="error", data_dir=data_dir,
            )
            counts["rejected"] += 1
            # This signal has reached its terminal outcome (rejected) — commit
            # the watermark past it now, per-signal rather than per-batch, so
            # a mid-batch crash can't re-triage it into a duplicate row later.
            state.set_cursor(WATERMARK_NAME, {"last_event_id": row["id"]}, data_dir)
            continue
        except Exception as exc:
            # Ollama itself is unreachable — stop the whole pass here. Don't
            # advance past this or any later signal; retry everything next time.
            events.log_event(
                SESSION_ID, turn_id, "error",
                {"context": "triage ollama call", "exception": type(exc).__name__, "message": str(exc)},
                level="error", data_dir=data_dir,
            )
            break

        purpose = result.get("purpose")
        events.log_event(
            SESSION_ID, turn_id, "triage",
            {
                "signal_event_id": row["id"],
                "classification": result["classification"],
                "purpose": purpose,
                "reason": result.get("reason", ""),
                "model": MODEL,
            },
            data_dir=data_dir,
        )
        counts["triaged"] += 1

        if result["classification"] == "propose":
            _dispatch_propose(row, result, purpose, turn_id, data_dir, counts)
        elif result["classification"] == "remember":
            _dispatch_remember(row, result, purpose, turn_id, data_dir, counts)

        # Terminal outcome reached for this signal — commit the watermark
        # past it now (see comment above; same reasoning applies here).
        state.set_cursor(WATERMARK_NAME, {"last_event_id": row["id"]}, data_dir)

    return counts


def run_pass(*, turn_id: str | None = None, data_dir: Path | None = None) -> dict:
    """Sanctioned entry point for the scheduler: run_triage_pass already
    handles the two expected failure modes (bad signal output, Ollama down)
    without raising. This is the outer safety net for anything truly
    unexpected — same pattern as nala.watchers.base.run_poll."""
    turn_id = turn_id or events.new_id()
    try:
        with loud_failure(SESSION_ID, turn_id, "triage pass", data_dir):
            return run_triage_pass(data_dir)
    except Exception:
        return {"triaged": 0, "proposed": 0, "rejected": 0}
