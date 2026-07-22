"""Access-token gate for non-localhost traffic (the cloudflared tunnel),
plus a CSRF Origin allow-list that applies independently of that
classification.

cloudflared forwards tunnel traffic as plain HTTP to 127.0.0.1, so
`request.client.host` is USELESS for telling tunnel traffic apart from real
localhost dev traffic — it reads "127.0.0.1" either way. The only reliable
signal is the forwarding headers cloudflared (and any reverse proxy) adds:
presence of CF-Connecting-IP or X-Forwarded-For means the request arrived
via the tunnel, never a request.client.host check alone.

CSRF: "no tunnel headers" used to mean "trust completely, skip every check"
— which is exactly what let any website the user's browser visits blind-POST
to 127.0.0.1:8642 and dispatch real actions (memory_write, capture_task)
with zero auth, confirmed live. is_allowed_origin is checked in serve.py's
middleware for every state-changing request REGARDLESS of tunnel/local
classification — it's a separate gate, not a replacement for the cookie
check above."""

import secrets

from nala.config import get_access_token

COOKIE_NAME = "nala_token"
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 3600  # 1 year

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FIXED_ALLOWED_ORIGINS = {"http://127.0.0.1:8642", "http://localhost:8642"}


def is_tunnel_request(headers) -> bool:
    """headers: a case-insensitive mapping (e.g. a Starlette Request.headers)."""
    return bool(headers.get("cf-connecting-ip") or headers.get("x-forwarded-for"))


def is_allowed_origin(origin: str | None, host: str | None) -> bool:
    """True only for the two fixed local-dev origins, or an https origin
    matching whatever Host the request itself carries (so the tunnel's
    hostname passes without hardcoding it — cloudflared forwards the
    original Host header). Missing Origin is never allowed: browsers always
    send it on a cross-origin (and same-origin) POST/PUT/PATCH/DELETE, so
    its absence means a non-browser client that hasn't been updated to send
    it, or a forged request stripping it — either way, refuse rather than
    guess."""
    if not origin:
        return False
    if origin in FIXED_ALLOWED_ORIGINS:
        return True
    return bool(host) and origin == f"https://{host}"


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
