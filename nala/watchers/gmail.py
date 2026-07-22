"""Polls Gmail (readonly) for messages added since the last known historyId.
First poll (no watermark yet) just establishes a baseline — nothing in the
existing inbox is "new", so it emits no signals for that poll."""

from pathlib import Path

from googleapiclient.errors import HttpError

from nala import state
from nala.watchers.base import Signal, Watcher


class GmailWatcher(Watcher):
    name = "gmail"
    interval_seconds = 120

    def __init__(self, service_factory=None, data_dir: Path | None = None):
        self._service_factory = service_factory or self._default_service_factory
        self.data_dir = data_dir

    def _default_service_factory(self):
        from googleapiclient.discovery import build

        from nala.google_auth import get_credentials
        creds = get_credentials(self.data_dir)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def poll(self) -> list[Signal]:
        service = self._service_factory()
        cursor = state.get_cursor(self.name, self.data_dir)
        last_history_id = cursor.get("history_id")

        if not last_history_id:
            profile = service.users().getProfile(userId="me").execute()
            state.set_cursor(self.name, {"history_id": profile["historyId"]}, self.data_dir)
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        page_token = None
        new_history_id = last_history_id
        while True:
            try:
                history_resp = service.users().history().list(
                    userId="me", startHistoryId=last_history_id,
                    historyTypes=["messageAdded"], pageToken=page_token,
                ).execute()
            except HttpError as exc:
                # Gmail retains history for only ~1 week; once startHistoryId expires
                # the call 404s on every poll forever. Re-baseline to the current
                # historyId and resume from now (the missed window is skipped) so the
                # watcher self-heals instead of flooding the feed with errors.
                if exc.resp.status == 404:
                    profile = service.users().getProfile(userId="me").execute()
                    state.set_cursor(self.name, {"history_id": profile["historyId"]}, self.data_dir)
                    return []
                raise

            for h in history_resp.get("history", []):
                for m in h.get("messagesAdded", []):
                    msg_id = m["message"]["id"]
                    if msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                    msg = service.users().messages().get(
                        userId="me", id=msg_id, format="metadata", metadataHeaders=["From", "Subject"],
                    ).execute()
                    headers = {hdr["name"]: hdr["value"] for hdr in msg.get("payload", {}).get("headers", [])}
                    signals.append(Signal(
                        source="gmail",
                        kind="new_message",
                        title=headers.get("Subject", "(no subject)"),
                        detail=(
                            f"from={headers.get('From', '?')} "
                            f"labels={','.join(msg.get('labelIds', []))} "
                            f"snippet={msg.get('snippet', '')}"
                        ),
                        ref=msg_id,
                    ))

            new_history_id = history_resp.get("historyId", new_history_id)
            page_token = history_resp.get("nextPageToken")
            if not page_token:
                break

        state.set_cursor(self.name, {"history_id": new_history_id}, self.data_dir)
        return signals
