"""Access-token gate for non-localhost traffic (the cloudflared tunnel).

cloudflared forwards tunnel traffic as plain HTTP to 127.0.0.1, so
`request.client.host` is USELESS for telling tunnel traffic apart from real
localhost dev traffic — it reads "127.0.0.1" either way. The only reliable
signal is the forwarding headers cloudflared (and any reverse proxy) adds:
presence of CF-Connecting-IP or X-Forwarded-For means the request arrived
via the tunnel, never a request.client.host check alone."""

import secrets

from nala.config import get_access_token

COOKIE_NAME = "nala_token"
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 3600  # 1 year


def is_tunnel_request(headers) -> bool:
    """headers: a case-insensitive mapping (e.g. a Starlette Request.headers)."""
    return bool(headers.get("cf-connecting-ip") or headers.get("x-forwarded-for"))


def is_authenticated(cookie_value: str | None) -> bool:
    token = get_access_token()
    if not token or not cookie_value:
        return False
    return secrets.compare_digest(cookie_value, token)


def verify_submitted_token(submitted: str) -> bool:
    token = get_access_token()
    if not token or not submitted:
        return False
    return secrets.compare_digest(submitted, token)
