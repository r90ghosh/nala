"""execute_action(intent) — the single chokepoint. Tools are dispatched only
from here. M2: boundary validation. Idempotency, atomicity/reconciliation,
spend ceiling, and confirm-gating land in M3."""

from dataclasses import dataclass, field
from pathlib import Path

from nala import events, tools, validation


@dataclass
class ActionResult:
    status: str  # done | failed | rejected
    message: str
    data: dict = field(default_factory=dict)


def execute_action(
    action_type: str,
    args: dict,
    *,
    turn_id: str,
    session_id: str,
    data_dir: Path | None = None,
) -> ActionResult:
    try:
        validated = validation.validate_intent(action_type, args)
    except validation.IntentValidationError as exc:
        payload = {"action_type": action_type, "args": args, "reason": exc.message}
        if exc.suggestion:
            payload["suggestion"] = exc.suggestion
        events.log_event(session_id, turn_id, "rejected", payload, level="error", data_dir=data_dir)
        msg = exc.message
        if exc.suggestion:
            msg += f" — did you mean '{exc.suggestion}'?"
        return ActionResult(status="rejected", message=msg)

    normalized_args = validated.model_dump(exclude={"action_type"})

    events.log_event(session_id, turn_id, "tool_call", {"action_type": action_type, "args": normalized_args}, data_dir=data_dir)

    try:
        with tools.dispatching():
            result = tools.TOOLS[action_type](**normalized_args)
    except Exception as exc:
        events.log_event(
            session_id, turn_id, "error",
            {"context": f"{action_type} dispatch", "exception": type(exc).__name__, "message": str(exc)},
            level="error", data_dir=data_dir,
        )
        return ActionResult(status="failed", message=f"{action_type} failed: {exc}")

    events.log_event(session_id, turn_id, "tool_result", {"action_type": action_type, "result": result}, data_dir=data_dir)

    if action_type == "report_status":
        lines = []
        for r in result:
            if "error" in r:
                lines.append(f"{r['repo']}: {r['error']}")
                continue
            flags = "(dirty)" if r["dirty"] else ""
            lines.append(f"{r['repo']}: {r['branch']} {flags}".rstrip())
        return ActionResult(status="done", message="\n".join(lines), data={"repos": result})

    if action_type == "capture_task":
        return ActionResult(status="done", message=f"captured task #{result['id']}: {result['title']}", data=result)

    return ActionResult(status="done", message=f"{action_type} succeeded", data=result if isinstance(result, dict) else {})
