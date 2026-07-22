import datetime
import json

import pytest

from nala.google_auth import GoogleAuthError, _token_path, get_credentials


def _write_token(data_dir, *, expiry, refresh_token):
    token_path = _token_path(data_dir)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps({
        "token": "fake-access-token",
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
        ],
        "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }))
    return token_path


def test_missing_token_raises_actionable_error(data_dir):
    with pytest.raises(GoogleAuthError) as exc_info:
        get_credentials()
    assert "python -m nala.google_auth" in str(exc_info.value)


def test_expired_token_without_refresh_token_raises(data_dir):
    _write_token(
        data_dir,
        expiry=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
        refresh_token=None,
    )

    with pytest.raises(GoogleAuthError):
        get_credentials()


def test_valid_unexpired_token_loads_without_network(data_dir):
    _write_token(
        data_dir,
        expiry=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        refresh_token="fake-refresh-token",
    )

    creds = get_credentials()

    assert creds.valid
    assert not creds.expired
