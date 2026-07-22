"""`python -m nala.google_auth` runs the InstalledAppFlow (local browser
server) once to mint ~/.nala/google_token.json (chmod 600). Subsequent loads
via get_credentials() refresh silently. This is the only place the
interactive OAuth flow runs — watchers never trigger it; a missing or
unrefreshable token is a loud GoogleAuthError, not a startup crash."""

import os
import stat
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from nala.config import get_data_dir, get_google_client_secret_path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

TOKEN_FILENAME = "google_token.json"


class GoogleAuthError(Exception):
    """Missing or unusable Google credentials — the operator must run
    `python -m nala.google_auth` interactively to fix this."""


def _token_path(data_dir: Path | None = None) -> Path:
    d = data_dir or get_data_dir()
    return d / TOKEN_FILENAME


def _write_token(creds: Credentials, token_path: Path) -> None:
    token_path.write_text(creds.to_json())
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)


def run_flow(data_dir: Path | None = None) -> Credentials:
    """Interactive: opens a local server so the operator can authorize in a
    browser. Never called automatically by a watcher or service."""
    secret_path = get_google_client_secret_path()
    if not secret_path.exists():
        raise GoogleAuthError(
            f"Google client secret not found at {secret_path} — set NALA_GOOGLE_CLIENT_SECRET"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    _write_token(creds, _token_path(data_dir))
    return creds


def get_credentials(data_dir: Path | None = None) -> Credentials:
    """Loads the saved token, refreshing silently if expired. Callers
    (watchers) must treat GoogleAuthError as a loud, degraded failure —
    never crash the process over it."""
    token_path = _token_path(data_dir)
    if not token_path.exists():
        raise GoogleAuthError("no Google token found — run: python -m nala.google_auth")

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _write_token(creds, token_path)
        return creds

    raise GoogleAuthError("Google token is invalid and cannot be refreshed — run: python -m nala.google_auth")


def main():
    creds = run_flow()
    print(f"Google credentials saved to {_token_path()} (scopes: {', '.join(SCOPES)})")
    print("valid:", creds.valid)


if __name__ == "__main__":
    main()
