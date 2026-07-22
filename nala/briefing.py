"""Composes the morning briefing: today's calendar, repo status (through the
chokepoint, reusing report_status), signals/triage activity since yesterday,
and yesterday+today spend — then asks claude-sonnet-5 to summarize it into
clean text (spend ledgered for that call too). Any section that's missing or
degraded is reported inline as a known-unknown; nothing is silently
dropped, and a failed summarization call falls back to the raw material
rather than losing it."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

from nala import chokepoint, db, events, spend
from nala.config import get_anthropic_api_key
from nala.errors import loud_failure
from nala.spend import SpendCeilingExceeded, check_ceiling, record_spend

SESSION_ID = "briefing"
BRIEFING_MODEL = "claude-sonnet-5"


def _fetch_todays_calendar(session_id: str, turn_id: str, data_dir: Path | None) -> str:
    try:
        with loud_failure(session_id, turn_id, "briefing calendar fetch", data_dir):
            from googleapiclient.discovery import build

            from nala.google_auth import get_credentials
            creds = get_credentials(data_dir)
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            now = datetime.now(timezone.utc)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
            resp = service.events().list(
                calendarId="primary", timeMin=now.isoformat(), timeMax=end_of_day.isoformat(),
                singleEvents=True, orderBy="startTime",
            ).execute()

            items = resp.get("items", [])
            if not items:
                return "no events remaining today"
            lines = []
            for event in items:
                start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
                lines.append(f"- {event.get('summary', '(no title)')} at {start}")
            return "\n".join(lines)
    except Exception as exc:
        return f"(calendar unavailable — known-unknown: {exc})"


def _fetch_repo_status(session_id: str, turn_id: str, data_dir: Path | None) -> str:
    result = chokepoint.execute_action("report_status", {}, turn_id=turn_id, session_id=session_id, data_dir=data_dir)
    return result.message


def _fetch_activity_summary(session_id: str, turn_id: str, data_dir: Path | None) -> str:
    try:
        with loud_failure(session_id, turn_id, "briefing activity summary", data_dir):
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            events.ensure_schema(data_dir)
            conn = db.connect(data_dir)
            try:
                signal_rows = conn.execute(
                    "SELECT payload_json FROM events WHERE type = 'signal' AND ts >= ? ORDER BY id", (cutoff,),
                ).fetchall()
                triage_rows = conn.execute(
                    "SELECT payload_json FROM events WHERE type = 'triage' AND ts >= ? ORDER BY id", (cutoff,),
                ).fetchall()
            finally:
                conn.close()

            if not signal_rows and not triage_rows:
                return "no new signals or triage activity in the last 24h"

            by_source: dict[str, int] = {}
            for row in signal_rows:
                payload = json.loads(row["payload_json"])
                by_source[payload["source"]] = by_source.get(payload["source"], 0) + 1

            by_classification: dict[str, int] = {}
            proposal_statuses: list[str] = []
            for row in triage_rows:
                payload = json.loads(row["payload_json"])
                cls = payload.get("classification")
                if cls:
                    by_classification[cls] = by_classification.get(cls, 0) + 1
                if "proposal_status" in payload:
                    proposal_statuses.append(payload["proposal_status"])

            lines = [f"signals by source: {by_source}", f"triage classifications: {by_classification}"]
            if proposal_statuses:
                lines.append(f"proposals raised: {len(proposal_statuses)} ({', '.join(proposal_statuses)})")
            return "\n".join(lines)
    except Exception as exc:
        return f"(activity summary unavailable — known-unknown: {exc})"


def _fetch_spend_summary(session_id: str, turn_id: str, data_dir: Path | None) -> str:
    try:
        with loud_failure(session_id, turn_id, "briefing spend summary", data_dir):
            yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
            return (
                f"yesterday: ${spend.total_for_day(yesterday, data_dir):.4f}, "
                f"today so far: ${spend.today_total(data_dir):.4f}"
            )
    except Exception as exc:
        return f"(spend summary unavailable — known-unknown: {exc})"


def _summarize(raw_material: str, turn_id: str, data_dir: Path | None) -> str:
    try:
        check_ceiling(data_dir)
    except SpendCeilingExceeded as exc:
        return f"(summary unavailable — spend ceiling reached: {exc})\n\n{raw_material}"

    client = anthropic.Anthropic(api_key=get_anthropic_api_key(), timeout=30.0, max_retries=2)
    try:
        response = client.messages.create(
            model=BRIEFING_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "Compose a concise morning briefing from this raw material for a solo "
                    "developer. Be direct, no fluff, short sections. If something is missing "
                    "or degraded, state it plainly as a known-unknown — never omit it "
                    "silently.\n\n" + raw_material
                ),
            }],
        )
    except anthropic.APIError as exc:
        return f"(summary unavailable — brain unreachable: {exc})\n\n{raw_material}"

    record_spend(
        turn_id=turn_id, model=BRIEFING_MODEL,
        input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
        data_dir=data_dir,
    )

    text_block = next((b for b in response.content if b.type == "text"), None)
    return text_block.text if text_block else raw_material


def compose_briefing(data_dir: Path | None = None) -> str:
    turn_id = events.new_id()

    raw_material = "\n\n".join([
        f"CALENDAR (today):\n{_fetch_todays_calendar(SESSION_ID, turn_id, data_dir)}",
        f"REPO STATUS:\n{_fetch_repo_status(SESSION_ID, turn_id, data_dir)}",
        f"ACTIVITY (last 24h):\n{_fetch_activity_summary(SESSION_ID, turn_id, data_dir)}",
        f"SPEND:\n{_fetch_spend_summary(SESSION_ID, turn_id, data_dir)}",
    ])

    briefing_text = _summarize(raw_material, turn_id, data_dir)

    events.log_event(SESSION_ID, turn_id, "briefing", {"text": briefing_text}, data_dir=data_dir)

    return briefing_text
