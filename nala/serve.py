"""`python -m nala.serve` — FastAPI on 127.0.0.1:8642 (localhost only). A thin
read/confirm/reject layer over the same data and the same chokepoint
functions the CLI uses — confirm/reject are NOT reimplemented here, they
call nala.chokepoint.confirm_action/reject_action directly, so a wildcard
token is rejected identically whether it came from the CLI or the browser.
The static page polls every 2s; no SSE needed at this scale."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from nala import auth, chokepoint, db, events, reconciler, spend
from nala.config import get_access_token

app = FastAPI(title="Nala")

STATIC_DIR = Path(__file__).parent / "static"
SESSION_ID = "web"


@app.middleware("http")
async def access_token_gate(request: Request, call_next):
    """Localhost dev traffic (no tunnel-forwarding headers) always passes
    freely. Tunnel traffic must carry the nala_token cookie."""
    if request.url.path == "/login" or not auth.is_tunnel_request(request.headers):
        return await call_next(request)

    if auth.is_authenticated(request.cookies.get(auth.COOKIE_NAME)):
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return HTMLResponse((STATIC_DIR / "login.html").read_text(), status_code=401)


@app.post("/login")
async def login(request: Request):
    body = await request.json()
    submitted = body.get("token", "")
    if not auth.verify_submitted_token(submitted):
        return JSONResponse({"error": "invalid token"}, status_code=401)

    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        auth.COOKIE_NAME, get_access_token(), max_age=auth.COOKIE_MAX_AGE_SECONDS,
        httponly=True, secure=True, samesite="lax",
    )
    return resp


@app.get("/api/events")
def api_get_events(since: int = 0):
    conn = db.connect()
    try:
        events.ensure_schema()
        rows = conn.execute(
            "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT 500", (since,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/api/actions")
def api_get_actions():
    return chokepoint.list_processed_actions()


@app.get("/api/status")
def api_get_status():
    return {
        "in_doubt": reconciler.in_doubt_count(),
        "today_spend_usd": spend.today_total(),
    }


@app.post("/api/actions/{token}/confirm")
def api_confirm(token: str):
    turn_id = events.new_id()
    result = chokepoint.confirm_action(token, turn_id=turn_id, session_id=SESSION_ID)
    return {"status": result.status, "message": result.message}


@app.post("/api/actions/{token}/reject")
def api_reject(token: str):
    turn_id = events.new_id()
    result = chokepoint.reject_action(token, turn_id=turn_id, session_id=SESSION_ID)
    return {"status": result.status, "message": result.message}


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text()


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8642)


if __name__ == "__main__":
    main()
