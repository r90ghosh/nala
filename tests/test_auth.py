"""Access-token gate. cloudflared forwards tunnel traffic as plain HTTP to
127.0.0.1, so request.client.host can't distinguish tunnel from real
localhost — these tests simulate tunnel traffic via header presence
(CF-Connecting-IP), exactly as the middleware itself detects it."""

from fastapi.testclient import TestClient

from nala import auth
from nala.serve import app

TUNNEL_HEADERS = {"cf-connecting-ip": "1.2.3.4"}
ORIGIN_HEADERS = {"origin": "http://127.0.0.1:8642"}  # matches auth.FIXED_ALLOWED_ORIGINS


def test_localhost_request_passes_without_cookie(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app)

    resp = client.get("/api/events")

    assert resp.status_code == 200


def test_tunnel_request_without_cookie_is_blocked(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app)

    resp = client.get("/api/events", headers=TUNNEL_HEADERS)

    assert resp.status_code == 401
    assert resp.json()["error"]


def test_tunnel_request_for_html_gets_login_page(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app)

    resp = client.get("/", headers=TUNNEL_HEADERS)

    assert resp.status_code == 401
    assert "tokenInput" in resp.text


def test_tunnel_request_with_wrong_token_cookie_is_rejected(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app)
    client.cookies.set(auth.COOKIE_NAME, "wrong-token")

    resp = client.get("/api/events", headers=TUNNEL_HEADERS)

    assert resp.status_code == 401


def test_login_with_wrong_token_is_rejected_and_sets_no_cookie(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app, headers=ORIGIN_HEADERS)

    resp = client.post("/login", json={"token": "wrong-token"})

    assert resp.status_code == 401
    assert auth.COOKIE_NAME not in resp.cookies


def test_login_with_correct_token_sets_cookie_and_then_tunnel_request_passes(monkeypatch, data_dir):
    # The cookie is Secure-flagged (matching real cloudflared-tunnel traffic,
    # which is HTTPS) — httpx's cookie jar correctly won't resend a Secure
    # cookie over plain http, so this round-trip test needs an https base_url
    # to faithfully exercise it, same as a real browser would. Origin must
    # match that same https://testserver — the dynamic Host-derived rule a
    # real tunnel hostname would satisfy.
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app, base_url="https://testserver", headers={"origin": "https://testserver"})

    login_resp = client.post("/login", json={"token": "correct-token"})
    assert login_resp.status_code == 200
    assert auth.COOKIE_NAME in login_resp.cookies

    resp = client.get("/api/events", headers=TUNNEL_HEADERS)
    assert resp.status_code == 200


def test_no_access_token_configured_fails_closed_for_tunnel_traffic(monkeypatch, data_dir):
    monkeypatch.delenv("NALA_ACCESS_TOKEN", raising=False)
    client = TestClient(app)

    resp = client.get("/api/events", headers=TUNNEL_HEADERS)

    assert resp.status_code == 401


def test_login_with_malformed_json_body_is_400_not_500(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app, headers=ORIGIN_HEADERS)

    resp = client.post("/login", content=b"not json at all", headers={"Content-Type": "application/json"})

    assert resp.status_code == 400


def test_login_with_non_dict_json_body_is_400_not_500(monkeypatch, data_dir):
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app, headers=ORIGIN_HEADERS)

    resp = client.post("/login", json=["not", "a", "dict"])

    assert resp.status_code == 400


# ---------------------------------------------------------------- CSRF origin gate

def test_post_with_foreign_origin_is_403(data_dir):
    client = TestClient(app, headers={"origin": "https://evil.example.com"})

    resp = client.post("/api/turn", json={"text": "hello"})

    assert resp.status_code == 403
    assert resp.json()["error"]


def test_post_with_no_origin_is_403(data_dir):
    client = TestClient(app)  # no Origin header at all

    resp = client.post("/api/turn", json={"text": "hello"})

    assert resp.status_code == 403


def test_post_with_allowed_localhost_origin_passes_csrf_gate(monkeypatch, data_dir, tmp_path):
    # Not asserting 200 here — that depends on the spend ceiling / brain call
    # succeeding — just that it gets PAST the CSRF gate (never a 403).
    monkeypatch.setenv("NALA_DAILY_CEILING_USD", "0.00")
    client = TestClient(app, headers=ORIGIN_HEADERS)

    resp = client.post("/api/turn", json={"text": "hello"})

    assert resp.status_code != 403


def test_get_requests_are_never_origin_gated(data_dir):
    client = TestClient(app)  # no Origin header

    resp = client.get("/api/events")

    assert resp.status_code == 200


def test_static_mount_still_requires_tunnel_auth(monkeypatch, data_dir):
    # Flagged as untested by the security review — GET /static/* must stay
    # behind the same tunnel-cookie gate as everything else non-/login.
    monkeypatch.setenv("NALA_ACCESS_TOKEN", "correct-token")
    client = TestClient(app)

    resp = client.get("/static/app.js", headers=TUNNEL_HEADERS)

    assert resp.status_code == 401
