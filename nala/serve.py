"""`python -m nala.serve` — FastAPI on 127.0.0.1:8642 (localhost only). A thin
read/confirm/reject/turn layer over the same data and the same
chokepoint/brain functions the CLI uses — nothing here reimplements that
logic, it's called directly, so behavior (including a wildcard-token
rejection) is identical whether it came from the CLI or the browser.
The static feed polls every few seconds; no SSE needed at this scale."""

import asyncio
import base64
import io
import time
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nala import auth, chokepoint, db, events, purposes, routing, spend, state, voice
from nala.brain import Brain
from nala.cli import process_turn
from nala.config import get_access_token, get_daily_ceiling, get_data_dir, get_ollama_url
from nala.errors import loud_failure
from nala.google_auth import get_credentials

MAX_VOICE_AUDIO_BYTES = 2 * 1024 * 1024
MAX_VOICE_AUDIO_DURATION_MS = 15_000

purposes.load_all()  # malformed manifest is a loud startup failure, not a silent skip

app = FastAPI(title="Nala")

STATIC_DIR = Path(__file__).parent / "static"
SESSION_ID = "web"
CHAT_SESSION_ID = "web-chat"
WATCHER_NAMES = ("gmail", "calendar", "git")

STATUS_CACHE_SECONDS = 60
_status_cache: dict = {"payload": None, "ts": 0.0}


@app.middleware("http")
async def access_token_gate(request: Request, call_next):
    """Two independent gates:

    1. CSRF Origin allow-list — every state-changing request (POST/PUT/
       PATCH/DELETE), regardless of tunnel-vs-local classification below.
       Local traffic used to skip this entirely, which is exactly what let
       a malicious page in the user's own browser blind-POST to
       127.0.0.1:8642 and dispatch real actions with zero auth (confirmed
       live). GET routes are unaffected — nothing here mutates state.

    2. Tunnel cookie auth — unchanged: localhost dev traffic (no
       tunnel-forwarding headers) passes freely once past gate 1; tunnel
       traffic must carry the nala_token cookie."""
    if request.method in auth.STATE_CHANGING_METHODS:
        origin = request.headers.get("origin")
        if not auth.is_allowed_origin(origin, request.headers.get("host")):
            events.log_event(
                "web", None, "rejected",
                {"reason": "CSRF origin check failed", "origin": origin, "path": request.url.path, "method": request.method},
                level="error",
            )
            return JSONResponse({"error": "forbidden — bad origin"}, status_code=403)

    if request.url.path == "/login" or not auth.is_tunnel_request(request.headers):
        return await call_next(request)

    if auth.is_authenticated(request.cookies.get(auth.COOKIE_NAME)):
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return HTMLResponse((STATIC_DIR / "login.html").read_text(), status_code=401)


async def _safe_json_body(request: Request) -> tuple[dict | None, JSONResponse | None]:
    """A malformed/non-JSON body must never 500 — request.json() raises on
    invalid JSON, and a non-dict body (e.g. a bare JSON array) would raise
    AttributeError on the first .get() call. Both are just a bad request."""
    try:
        body = await request.json()
    except Exception:
        return None, JSONResponse({"error": "bad request"}, status_code=400)
    if not isinstance(body, dict):
        return None, JSONResponse({"error": "bad request"}, status_code=400)
    return body, None


@app.post("/login")
async def login(request: Request):
    body, err = await _safe_json_body(request)
    if err is not None:
        return err

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
    """Repo status + in-doubt count, run through the chokepoint (reusing
    report_status exactly as the CLI does) and cached 60s — report_status
    shells a git subprocess per repo, not worth re-running on every poll."""
    now = time.monotonic()
    cached = _status_cache["payload"]
    if cached is not None and (now - _status_cache["ts"]) < STATUS_CACHE_SECONDS:
        return cached

    turn_id = events.new_id()
    result = chokepoint.execute_action("report_status", {}, turn_id=turn_id, session_id=SESSION_ID, actor="status-cache")
    payload = {
        "status": result.status,
        "message": result.message,
        "repos": result.data.get("repos", []),
        "in_doubt": result.data.get("in_doubt_count", 0),
    }
    _status_cache["payload"] = payload
    _status_cache["ts"] = now
    return payload


@app.get("/api/spend")
def api_get_spend():
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    return {
        "today_total": spend.today_total(),
        "yesterday_total": spend.total_for_day(yesterday),
        "ceiling": get_daily_ceiling(),
        "by_model": spend.breakdown_for_day(today),
    }


@app.get("/api/health")
def api_get_health():
    """Best-effort, never blocks the page: a 1s-timeout Ollama ping and a
    Google credential check, both swallowed on failure rather than logged —
    logging every transient health-check miss as a level='error' event would
    flood the observability feed this same page is trying to show cleanly."""
    watchers = {name: {"last_poll": state.get_updated_at(name)} for name in WATCHER_NAMES}

    ollama_ok = False
    try:
        resp = httpx.get(f"{get_ollama_url()}/models", timeout=1.0)
        ollama_ok = resp.status_code == 200
    except Exception:
        ollama_ok = False

    google_ok = False
    try:
        get_credentials()
        google_ok = True
    except Exception:
        google_ok = False

    return {"watchers": watchers, "ollama_reachable": ollama_ok, "google_token_ok": google_ok}


@app.get("/api/routing")
def api_get_routing():
    return routing.get_routes()


PURPOSE_DISPLAY_ORDER = ["projects", "finance", "baby", "relationships", "home", "news", "interests", "purchase"]


@app.get("/api/purposes")
def api_get_purposes():
    """Backs the purpose rail — real risk profiles from the manifests, not
    the placeholder 'M5' tags M4/M5 shipped with."""
    manifests = purposes.load_all()
    return [
        {"name": name, "display_name": manifests[name].display_name, "risk_profile": manifests[name].risk_profile}
        for name in PURPOSE_DISPLAY_ORDER
    ]


def _run_turn_sync(text: str, turn_id: str | None = None) -> tuple[str, chokepoint.ActionResult]:
    turn_id = turn_id or events.new_id()
    brain = Brain()
    try:
        with loud_failure(CHAT_SESSION_ID, turn_id, "web turn"):
            result = process_turn(text, brain=brain, session_id=CHAT_SESSION_ID, turn_id=turn_id)
    except Exception as exc:
        result = chokepoint.ActionResult(status="failed", message=f"turn failed unexpectedly: {exc}")
    return turn_id, result


@app.post("/api/turn")
async def api_turn(request: Request):
    body, err = await _safe_json_body(request)
    if err is not None:
        return err

    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    # process_turn is sync and does real network I/O (brain, chokepoint tool
    # dispatch) — never run it inline in the async handler, it would block
    # the whole event loop (and every other watcher/request) for its duration.
    turn_id, result = await asyncio.to_thread(_run_turn_sync, text)
    turn_events = events.events_for_turn(turn_id)

    confirm_token = None
    if result.status == "awaiting_confirm":
        rows = chokepoint.list_processed_actions(limit=1000)
        match = next((r for r in rows if r["turn_id"] == turn_id), None)
        if match:
            confirm_token = match["idempotency_key"][:8]

    return {
        "turn_id": turn_id,
        "reply_text": result.message,
        "status": result.status,
        "confirm_token": confirm_token,
        "events": [dict(row) for row in turn_events],
    }


@app.get("/api/voice/warmup")
def api_voice_warmup():
    """Forces both voice models to load now, ahead of the first real PTT
    request — the load itself takes several seconds and nobody wants that
    latency mid-conversation."""
    voice.warmup()
    return {"status": "ready"}


@app.post("/api/voice/turn")
async def api_voice_turn(audio: UploadFile | None = File(None)):
    """Same pipeline as /api/turn, but audio in, audio out: save the upload,
    transcribe, gate on low confidence (loud-failure clause 3 — ask rather
    than guess), run process_turn, synthesize the reply. Auth-gated by the
    same middleware as every other /api/ route."""
    if audio is None:
        return JSONResponse({"error": "audio is required"}, status_code=400)

    raw = await audio.read()
    if not raw:
        return JSONResponse({"error": "audio is required"}, status_code=400)
    if len(raw) > MAX_VOICE_AUDIO_BYTES:
        return JSONResponse({"error": f"audio exceeds the {MAX_VOICE_AUDIO_BYTES}-byte limit"}, status_code=413)

    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            rate = w.getframerate()
            duration_ms = int((w.getnframes() / rate) * 1000) if rate else 0
    except (wave.Error, EOFError) as exc:
        return JSONResponse({"error": f"malformed audio: {exc}"}, status_code=400)

    if duration_ms > MAX_VOICE_AUDIO_DURATION_MS:
        return JSONResponse({"error": f"audio exceeds the {MAX_VOICE_AUDIO_DURATION_MS}ms limit"}, status_code=413)

    turn_id = events.new_id()
    tmp_dir = get_data_dir() / "tmp_voice"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    upload_path = tmp_dir / f"upload-{turn_id}.wav"
    upload_path.write_bytes(raw)
    try:
        stt_result = await asyncio.to_thread(voice.transcribe, upload_path, turn_id=turn_id)
    finally:
        upload_path.unlink(missing_ok=True)

    ask_repeat, reason = voice.gate_low_confidence(stt_result)
    if ask_repeat:
        events.log_event(
            CHAT_SESSION_ID, turn_id, "rejected",
            {"reason": f"low-confidence transcription — asking to repeat: {reason}", "transcript": stt_result["text"]},
            level="error",
        )
        return {"ask_repeat": True, "reason": reason, "turn_id": turn_id, "transcript": stt_result["text"]}

    # process_turn and synthesize are both sync and do real work (brain call,
    # chokepoint dispatch, TTS inference) — never run them inline in the
    # async handler, same reasoning as /api/turn's own to_thread call.
    _, result = await asyncio.to_thread(_run_turn_sync, stt_result["text"], turn_id)
    reply_audio = await asyncio.to_thread(voice.synthesize, result.message, turn_id=turn_id)

    turn_events = events.events_for_turn(turn_id)
    confirm_token = None
    if result.status == "awaiting_confirm":
        rows = chokepoint.list_processed_actions(limit=1000)
        match = next((r for r in rows if r["turn_id"] == turn_id), None)
        if match:
            confirm_token = match["idempotency_key"][:8]

    return {
        "turn_id": turn_id,
        "transcript": stt_result["text"],
        "reply_text": result.message,
        "status": result.status,
        "confirm_token": confirm_token,
        "events": [dict(row) for row in turn_events],
        "audio_b64": base64.b64encode(reply_audio).decode("ascii"),
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


@app.post("/api/actions/{token}/dismiss")
def api_dismiss(token: str):
    turn_id = events.new_id()
    result = chokepoint.dismiss_action(token, turn_id=turn_id, session_id=SESSION_ID)
    return {"status": result.status, "message": result.message}


@app.get("/api/memory")
def api_get_memory(label: str | None = None, kind: str | None = None, purpose_scope: str | None = None):
    """Backs the Memory tab's graph view — a thin wrapper over the same
    memory_recall dispatch chat uses, so an invalid kind/purpose_scope gets
    the same boundary-validation rejection either way."""
    args: dict = {}
    if label:
        args["label"] = label
    if kind:
        args["kind"] = kind
    if purpose_scope:
        args["purpose_scope"] = purpose_scope

    turn_id = events.new_id()
    result = chokepoint.execute_action("memory_recall", args, turn_id=turn_id, session_id=SESSION_ID)
    if result.status != "done":
        return JSONResponse({"error": result.message}, status_code=400)
    return result.data


@app.get("/api/memory/writes")
def api_get_memory_writes():
    """Recent memory_write ledger rows for the Memory tab's activity panel —
    same list_processed_actions() the action queue uses, just filtered."""
    rows = chokepoint.list_processed_actions(limit=500)
    return [r for r in rows if r["action_type"] == "memory_write"][:30]


@app.post("/api/memory/undo/{node_id}")
def api_undo_memory_node(node_id: str):
    """"Undo" for a memory write is a fresh delete_node dispatch through the
    chokepoint, not resolving an old ledger row — memory_write is reversible
    and this call carries no purpose, so it dispatches immediately, same as
    any other direct user action."""
    turn_id = events.new_id()
    result = chokepoint.execute_action(
        "memory_write", {"op": "delete_node", "node_id": node_id},
        turn_id=turn_id, session_id=SESSION_ID,
    )
    return {"status": result.status, "message": result.message}


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8642)


if __name__ == "__main__":
    main()
