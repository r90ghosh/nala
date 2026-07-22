"""Consumes un-triaged signal events (nala.state watermark) and classifies
each with the local model (llama3.2:3b via Ollama's OpenAI-compatible
/chat/completions) into ignore | remember | propose.

Two distinct failure modes, handled differently:
- Ollama itself is unreachable: a batch-level failure. Loud (logged,
  level='error'), and the whole pass stops there without advancing the
  watermark past this or any later signal — everything is retried next pass.
- A single signal's model output is malformed or out-of-set: loud reject
  for that signal specifically (logged, level='error'), but the watermark
  DOES advance past it — retrying the exact same garbage forever helps no
  one, and other signals in the same batch are unaffected.

'propose' with valid capture_task args is routed through
chokepoint.execute_action(..., force_confirm=True) — every proactively
proposed action requires a confirm in M4, regardless of the action's own
reversibility tag. Boundary validation of the proposed args is chokepoint's
job, not re-implemented here."""

import json
from pathlib import Path

import httpx

from nala import chokepoint, db, events, spend, state
from nala.config import get_ollama_url
from nala.errors import loud_failure

MODEL = "llama3.2:3b"
SESSION_ID = "triage"
WATERMARK_NAME = "triage"

VALID_CLASSIFICATIONS = {"ignore", "remember", "propose"}


class TriageError(Exception):
    """The model's output for one signal couldn't be used — malformed JSON,
    missing fields, or an out-of-set classification. Distinct from Ollama
    being unreachable, which is a batch-level failure."""


def _build_prompt(signal_payload: dict) -> str:
    return (
        "You triage incoming signals for a personal proactive assistant. Classify the "
        "signal as exactly one of: ignore, remember, propose.\n"
        "- ignore: not worth remembering or acting on.\n"
        "- remember: worth keeping as context, no action needed right now.\n"
        "- propose: worth proposing a concrete task capture.\n\n"
        f"Signal: {json.dumps(signal_payload)}\n\n"
        "Respond with ONLY a JSON object, no other text:\n"
        '{"classification": "ignore|remember|propose", "reason": "one line", '
        '"capture_task": {"title": "...", "project": "...", "priority": "...", '
        '"category": "..."} or null}'
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


def run_triage_pass(data_dir: Path | None = None) -> dict:
    signals = _fetch_untriaged_signals(data_dir)
    if not signals:
        return {"triaged": 0, "proposed": 0, "rejected": 0}

    counts = {"triaged": 0, "proposed": 0, "rejected": 0}
    last_id = None

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
            last_id = row["id"]
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

        events.log_event(
            SESSION_ID, turn_id, "triage",
            {
                "signal_event_id": row["id"],
                "classification": result["classification"],
                "reason": result.get("reason", ""),
                "model": MODEL,
            },
            data_dir=data_dir,
        )
        counts["triaged"] += 1

        if result["classification"] == "propose":
            proposal = result.get("capture_task")
            if isinstance(proposal, dict):
                action_result = chokepoint.execute_action(
                    "capture_task", proposal,
                    turn_id=turn_id, session_id=SESSION_ID, data_dir=data_dir,
                    force_confirm=True,
                )
                counts["proposed"] += 1
                events.log_event(
                    SESSION_ID, turn_id, "triage",
                    {
                        "signal_event_id": row["id"],
                        "proposal_status": action_result.status,
                        "proposal_message": action_result.message,
                    },
                    data_dir=data_dir,
                )
            else:
                events.log_event(
                    SESSION_ID, turn_id, "rejected",
                    {"signal_event_id": row["id"], "reason": "propose classification missing valid capture_task args"},
                    level="error", data_dir=data_dir,
                )

        last_id = row["id"]

    if last_id is not None:
        state.set_cursor(WATERMARK_NAME, {"last_event_id": last_id}, data_dir)

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
