"""Polls Google Calendar (readonly) for events starting in the next 48h that
haven't been signaled yet, plus re-signals an already-seen event if its
start time changes."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from nala import state
from nala.watchers.base import Signal, Watcher

LOOKAHEAD_HOURS = 48


class CalendarWatcher(Watcher):
    name = "calendar"
    interval_seconds = 300

    def __init__(self, service_factory=None, data_dir: Path | None = None):
        self._service_factory = service_factory or self._default_service_factory
        self.data_dir = data_dir

    def _default_service_factory(self):
        from googleapiclient.discovery import build

        from nala.google_auth import get_credentials
        creds = get_credentials(self.data_dir)
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def poll(self) -> list[Signal]:
        service = self._service_factory()
        cursor = state.get_cursor(self.name, self.data_dir)
        signaled: dict = cursor.get("signaled", {})  # event_id -> last-signaled start time

        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=LOOKAHEAD_HOURS)

        resp = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=horizon.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        signals: list[Signal] = []
        new_signaled = dict(signaled)

        for event in resp.get("items", []):
            event_id = event["id"]
            start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
            prev_start = signaled.get(event_id)

            if prev_start is None:
                kind = "upcoming_event"
            elif prev_start != start:
                kind = "event_changed"
            else:
                continue  # already signaled, unchanged

            signals.append(Signal(
                source="calendar",
                kind=kind,
                title=event.get("summary", "(no title)"),
                detail=f"starts {start}",
                ref=event_id,
            ))
            new_signaled[event_id] = start

        state.set_cursor(self.name, {"signaled": new_signaled}, self.data_dir)
        return signals
