"""execute_action(intent) — the single chokepoint. Tools are dispatched only
from here.

Precondition block (in order): spend ceiling, then boundary validation.
report_status is a pure read and bypasses the idempotency ledger entirely —
it also triggers the reconciler and always reports "in-doubt actions: N",
never a bare "all clear". Everything else (capture_task, archive_task) goes
through the idempotency ledger with a two-phase commit: pending row -> side
effect -> terminal state. Irreversible actions land in awaiting_confirm
instead of pending until confirm_action() supplies a matching token.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from nala import events, reconciler, tools, validation
from nala.db import connect, ensure_processed_actions
from nala.errors import loud_failure
from nala.spend import SpendCeilingExceeded, check_ceiling

# Test-only injection point: a callable(checkpoint_name) that can raise to
# simulate a hard process kill at a specific point in the two-phase commit.
# No-op in production.
_crash_hook = None

_HEX_TOKEN = re.compile(r"^[0-9a-f]+$")


@dataclass
class ActionResult:
    status: str  # done | failed | rejected | awaiting_confirm | pending
    message: str
    data: dict = field(default_factory=dict)


def compute_key(action_type: str, args: dict, turn_id: str) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    raw = f"{action_type}{canonical}{turn_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _checkpoint(name: str) -> None:
    if _crash_hook is not None:
        _crash_hook(name)


def execute_action(
    action_type: str,
    args: dict,
    *,
    turn_id: str,
    session_id: str,
    data_dir: Path | None = None,
    force_confirm: bool = False,
) -> ActionResult:
    """force_confirm: proactive callers (triage, M4+) pass True to require a
    confirm regardless of the action's own reversibility tag — in M4, every
    proactively-proposed action is gated, full stop; per-purpose risk
    profiles (auto/notify/confirm) arrive with purposes in M5."""
    try:
        check_ceiling(data_dir)
    except SpendCeilingExceeded as exc:
        events.log_event(session_id, turn_id, "rejected", {"reason": str(exc)}, level="error", data_dir=data_dir)
        return ActionResult(status="rejected", message=f"refused: {exc}")

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

    if action_type == "report_status":
        return _handle_report_status(session_id, turn_id, data_dir)

    reversibility = validation.REVERSIBILITY[action_type]
    normalized_args = validated.model_dump(exclude={"action_type"})
    key = compute_key(action_type, normalized_args, turn_id)

    conn = connect(data_dir)
    ensure_processed_actions(conn)
    existing = conn.execute("SELECT * FROM processed_actions WHERE idempotency_key = ?", (key,)).fetchone()

    if existing:
        conn.close()
        return _resolve_row(existing, key, session_id, turn_id, data_dir)

    # Test-only injection point: a concurrent same-key caller can commit its
    # own row in this exact window (after our SELECT above, before our INSERT
    # below). _checkpoint lets tests simulate that race deterministically.
    _checkpoint("before_insert")

    now = datetime.now(timezone.utc).isoformat()
    insert_status = "awaiting_confirm" if (reversibility == "irreversible" or force_confirm) else "pending"
    cur = conn.execute(
        "INSERT OR IGNORE INTO processed_actions "
        "(idempotency_key, turn_id, action_type, reversibility, args_json, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (key, turn_id, action_type, reversibility, json.dumps(normalized_args), insert_status, now),
    )
    conn.commit()
    won_insert = cur.rowcount == 1

    if not won_insert:
        # A concurrent caller with the same key already committed a row first —
        # resolve against whatever it landed as instead of dispatching twice.
        row = conn.execute("SELECT * FROM processed_actions WHERE idempotency_key = ?", (key,)).fetchone()
        conn.close()
        return _resolve_row(row, key, session_id, turn_id, data_dir)

    conn.close()

    if insert_status == "awaiting_confirm":
        return ActionResult(
            status="awaiting_confirm",
            message=f"irreversible action requires confirmation — type: confirm {key[:8]}",
        )

    return _dispatch_and_terminate(key, action_type, normalized_args, session_id, turn_id, data_dir)


def _resolve_row(row, key: str, session_id: str, turn_id: str, data_dir: Path | None) -> ActionResult:
    """Given an existing processed_actions row (whether found on the initial
    lookup or discovered after losing an INSERT OR IGNORE race), report its
    status without ever dispatching a second side effect."""
    if row["status"] in ("done", "failed", "rejected"):
        return _replay(row, session_id, turn_id, data_dir)
    if row["status"] == "awaiting_confirm":
        return ActionResult(
            status="awaiting_confirm",
            message=f"irreversible action requires confirmation — type: confirm {key[:8]}",
        )
    return ActionResult(
        status="pending",
        message="this action is already in flight (in-doubt); the reconciler will resolve it",
    )


def _find_awaiting_confirm_row(token: str, *, session_id: str, turn_id: str, data_dir: Path | None):
    """Shared by confirm_action and reject_action (CLI and web both call
    these — this is the one place token resolution happens). Returns
    (row, None) on a clean single match, or (None, ActionResult) with the
    rejection already logged."""
    token = token.strip().lower()

    if not token or not _HEX_TOKEN.match(token):
        events.log_event(
            session_id, turn_id, "rejected",
            {"reason": "confirm token must be hex characters only", "token": token},
            level="error", data_dir=data_dir,
        )
        return None, ActionResult(status="rejected", message=f"invalid confirm token '{token}' — expected a hex idempotency-key prefix")

    conn = connect(data_dir)
    ensure_processed_actions(conn)
    # Match in Python against the literal token — never SQL LIKE on raw user
    # input, since '%'/'_' are LIKE wildcards that would match any row.
    candidates = conn.execute("SELECT * FROM processed_actions WHERE status='awaiting_confirm'").fetchall()
    conn.close()
    matches = [r for r in candidates if r["idempotency_key"].startswith(token)]

    if not matches:
        events.log_event(session_id, turn_id, "rejected", {"reason": "no pending confirmation matches token", "token": token}, level="error", data_dir=data_dir)
        return None, ActionResult(status="rejected", message=f"no pending confirmation matches '{token}'")

    if len(matches) > 1:
        events.log_event(
            session_id, turn_id, "rejected",
            {"reason": "ambiguous confirm token", "token": token, "match_count": len(matches)},
            level="error", data_dir=data_dir,
        )
        return None, ActionResult(
            status="rejected",
            message=f"ambiguous token '{token}' matches {len(matches)} pending confirmations — provide more characters",
        )

    return matches[0], None


def confirm_action(token: str, *, turn_id: str, session_id: str, data_dir: Path | None = None) -> ActionResult:
    row, rejection = _find_awaiting_confirm_row(token, session_id=session_id, turn_id=turn_id, data_dir=data_dir)
    if rejection is not None:
        return rejection

    key = row["idempotency_key"]
    action_type = row["action_type"]
    normalized_args = json.loads(row["args_json"])

    try:
        check_ceiling(data_dir)
    except SpendCeilingExceeded as exc:
        now = datetime.now(timezone.utc).isoformat()
        conn = connect(data_dir)
        ensure_processed_actions(conn)
        conn.execute(
            "UPDATE processed_actions SET status='rejected', error_json=?, resolved_at=? WHERE idempotency_key=? AND status='awaiting_confirm'",
            (json.dumps({"reason": str(exc)}), now, key),
        )
        conn.commit()
        conn.close()
        events.log_event(session_id, turn_id, "rejected", {"reason": str(exc)}, level="error", data_dir=data_dir)
        return ActionResult(status="rejected", message=f"refused: {exc}")

    conn = connect(data_dir)
    ensure_processed_actions(conn)
    cur = conn.execute("UPDATE processed_actions SET status='pending' WHERE idempotency_key=? AND status='awaiting_confirm'", (key,))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        events.log_event(session_id, turn_id, "rejected", {"reason": "action was already resolved by another confirm/reject", "idempotency_key": key}, level="error", data_dir=data_dir)
        return ActionResult(status="rejected", message="this action was already resolved (confirmed or rejected elsewhere)")

    return _dispatch_and_terminate(key, action_type, normalized_args, session_id, turn_id, data_dir)


def reject_action(token: str, *, turn_id: str, session_id: str, data_dir: Path | None = None) -> ActionResult:
    row, rejection = _find_awaiting_confirm_row(token, session_id=session_id, turn_id=turn_id, data_dir=data_dir)
    if rejection is not None:
        return rejection

    key = row["idempotency_key"]
    now = datetime.now(timezone.utc).isoformat()

    conn = connect(data_dir)
    ensure_processed_actions(conn)
    cur = conn.execute(
        "UPDATE processed_actions SET status='rejected', error_json=?, resolved_at=? WHERE idempotency_key=? AND status='awaiting_confirm'",
        (json.dumps({"reason": "rejected by operator"}), now, key),
    )
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        events.log_event(session_id, turn_id, "rejected", {"reason": "action was already resolved by another confirm/reject", "idempotency_key": key}, level="error", data_dir=data_dir)
        return ActionResult(status="rejected", message="this action was already resolved (confirmed or rejected elsewhere)")

    events.log_event(session_id, turn_id, "rejected", {"reason": "operator rejected proposed action", "idempotency_key": key}, data_dir=data_dir)
    return ActionResult(status="rejected", message=f"rejected {row['action_type']} #{key[:8]}")


def _dispatch_and_terminate(key: str, action_type: str, args: dict, session_id: str, turn_id: str, data_dir: Path | None) -> ActionResult:
    events.log_event(session_id, turn_id, "tool_call", {"action_type": action_type, "args": args}, data_dir=data_dir)
    _checkpoint("after_pending_commit")

    call_args = dict(args)
    if action_type == "capture_task":
        call_args["client_ref"] = key

    try:
        with loud_failure(session_id, turn_id, f"{action_type} dispatch", data_dir):
            with tools.dispatching() as ticket:
                result = tools.dispatch(action_type, call_args, ticket)
    except Exception as exc:
        _mark_terminal(key, "failed", error={"exception": type(exc).__name__, "message": str(exc)}, data_dir=data_dir)
        return ActionResult(status="failed", message=f"{action_type} failed: {exc}")

    _checkpoint("after_side_effect")

    _mark_terminal(key, "done", result=result, data_dir=data_dir)
    events.log_event(session_id, turn_id, "tool_result", {"action_type": action_type, "result": result}, data_dir=data_dir)

    if action_type == "capture_task":
        message = f"captured task #{result['id']}: {result['title']}"
    else:
        message = f"{action_type} succeeded"
    return ActionResult(status="done", message=message, data=result if isinstance(result, dict) else {})


def _mark_terminal(key: str, status: str, *, result: dict | None = None, error: dict | None = None, data_dir: Path | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(data_dir)
    ensure_processed_actions(conn)
    conn.execute(
        "UPDATE processed_actions SET status=?, result_json=?, error_json=?, resolved_at=? WHERE idempotency_key=?",
        (status, json.dumps(result) if result is not None else None, json.dumps(error) if error is not None else None, now, key),
    )
    conn.commit()
    conn.close()


def _replay(row, session_id: str, turn_id: str, data_dir: Path | None) -> ActionResult:
    result = json.loads(row["result_json"]) if row["result_json"] else None
    error = json.loads(row["error_json"]) if row["error_json"] else None
    events.log_event(session_id, turn_id, "tool_result", {"replayed": True, "status": row["status"]}, data_dir=data_dir)

    if row["status"] == "done":
        message = f"(already done — replayed) captured task #{result['id']}" if result and "id" in result else "(already done — replayed)"
        return ActionResult(status="done", message=message, data=result or {})
    if row["status"] == "failed":
        return ActionResult(status="failed", message=f"(already failed — replayed) {error}", data={})
    return ActionResult(status="rejected", message=f"(already rejected — replayed) {error}", data={})


def _handle_report_status(session_id: str, turn_id: str, data_dir: Path | None) -> ActionResult:
    reconcile_error = None
    try:
        with loud_failure(session_id, turn_id, "reconciler.reconcile", data_dir):
            reconciler.reconcile(data_dir=data_dir, session_id=session_id, turn_id=turn_id)
    except Exception as exc:
        reconcile_error = str(exc)

    events.log_event(session_id, turn_id, "tool_call", {"action_type": "report_status"}, data_dir=data_dir)

    repos_error = None
    repos: list = []
    try:
        with loud_failure(session_id, turn_id, "report_status dispatch", data_dir):
            with tools.dispatching() as ticket:
                repos = tools.dispatch("report_status", {}, ticket)
    except Exception as exc:
        repos_error = str(exc)

    events.log_event(session_id, turn_id, "tool_result", {"action_type": "report_status", "error": repos_error}, data_dir=data_dir)

    lines = []
    if repos_error:
        lines.append(f"report_status degraded: {repos_error}")
    else:
        for r in repos:
            if "error" in r:
                lines.append(f"{r['repo']}: {r['error']}")
                continue
            flags = "(dirty)" if r["dirty"] else ""
            lines.append(f"{r['repo']}: {r['branch']} {flags}".rstrip())

    in_doubt = reconciler.in_doubt_count(data_dir)
    if reconcile_error:
        lines.append(f"in-doubt actions: {in_doubt} (reconciliation failed: {reconcile_error})")
    else:
        lines.append(f"in-doubt actions: {in_doubt}")

    status = "failed" if repos_error else "done"
    return ActionResult(status=status, message="\n".join(lines), data={"repos": repos, "in_doubt_count": in_doubt})
