# Nala — Project Instructions

Voice-first, proactive, multipurpose personal assistant running locally on the Mac.
**PLAN.md is the authoritative spec** — read its "Reliability spine" section before touching
the action path. Repo: https://github.com/r90ghosh/nala

## Status

- **Session 1 complete (2026-07-21):** M0–M3 spine built, reviewed, hardened. Typed-text
  CLI works end to end against the real backlog (:8421) and real Claude API. 24 tests
  green. Commits M0→M3 + review-fix pushed to main.
- **Session 2 complete (2026-07-22):** M4 — watchers (gmail, calendar, git) → signal
  events, Ollama (llama3.2:3b) triage loop, morning briefing (`--briefing`), FastAPI web
  feed on :8642. 66 tests green. Commits M4a→M4d pushed to main. Verified end to end
  against the real backlog, real Claude API, the real Ollama instance, and real Google
  Calendar/Gmail (read-only) — including one real case of the local model proposing a
  malformed capture_task, which the chokepoint correctly rejected rather than executing.
- **Session 3 complete (2026-07-22):** M5 — graph memory (`nala/memory.py`:
  nodes/edges/observations, provenance non-negotiable — source+source_ref+timestamp
  required on every observation), purposes + risk profiles (`nala/purposes.py` +
  `purposes/<name>/manifest.yaml` for all 8, loaded/validated at startup — a malformed
  manifest is a loud process-start failure), chokepoint purpose-aware gating
  (read_only rejects writes / notify_only lands as a dismissible no-side-effect
  `notified` row / act_confirm behaves as `awaiting_confirm` did in M4) retiring M4's
  blanket `force_confirm` special case, triage v2 (classification now also assigns a
  purpose — unknown never guesses into a permissive one — and 'remember' actually
  proposes a `memory_write` instead of being a no-op label), the Memory tab (hand-rolled
  SVG force-directed graph, node click → observations + provenance chips, purpose
  filter pills, search, recent-writes feed with undo via `delete_node`),
  `python -m nala.seed_memory`, and brain integration (`memory_recall` context injected
  as the system prompt before every chat turn; `memory_write`/`memory_recall` in the
  tool schema so chat can act on "remember that X" directly). 165 tests green. Commits
  M5a→M5c pushed to main. Verified end to end against the real Claude API: a live chat
  turn recalled the seeded graph and correctly proposed+dispatched a `memory_write` with
  provenance; the verification-only node was deleted afterward so no fabricated data
  persists in the real `~/.nala/memory.db`.
- **Session 4 complete (2026-07-22):** M6 — fully local voice. `nala/voice.py`: STT
  (parakeet-mlx, `mlx-community/parakeet-tdt-0.6b-v2`) and TTS (mlx-audio Kokoro,
  `mlx-community/Kokoro-82M-bf16`, voice af_heart), both lazy-loaded singletons, `GET
  /api/voice/warmup` to preload. `POST /api/voice/turn`: WAV upload → transcribe →
  low-confidence gate (ask_repeat, never runs the turn — loud-failure clause 3) →
  `process_turn` (same path as `/api/turn`) → synthesize the reply →
  `{transcript, reply_text, status, confirm_token, events, audio_b64}`. Client: push-to-talk
  everywhere (top-bar mic + a big round hero button in Chat), hand-rolled Float32→WAV
  encoding via `ScriptProcessorNode` (~30 lines, no build step), autoplay of the reply audio
  reusing the same `AudioContext` the PTT press already unlocked (the iOS gesture trick),
  toast notifications for `ask_repeat` and for PTT used outside Chat mode. Purpose rail is
  real now — `GET /api/purposes` backs it, 'M5' tags gone, all 8 shown as plain informational
  rows (not buttons) with their actual risk badges, since a purpose activates per-signal, not
  per-session. `--briefing --speak` synthesizes and `afplay`s the briefing. 190 tests green.
  Commits M6a→M6b pushed to main.
  - **Real finding beyond the spec:** MLX arrays/streams are thread-affine
    (`mx.new_stream`'s own docstring says as much). A model loaded on one thread and used
    from another — which `asyncio.to_thread` can and does do across separate calls — broke
    live with `RuntimeError: There is no Stream(cpu, N) in current thread`, reproduced
    against the running server before the fix. Fixed by funneling every MLX-touching call
    (model load and inference, both STT and TTS) through one dedicated single-worker
    `ThreadPoolExecutor` in `nala/voice.py`, so it always runs on the same thread for the
    process's lifetime; `asyncio.to_thread` still wraps the outer calls so the event loop
    never blocks.
  - **Also found (contrary to the spec's uncertainty):** parakeet-mlx DOES expose confidence
    (`AlignedSentence.confidence`) — used as a secondary signal, not primary: a real test
    against ~200ms of silence still produced a hallucinated "Yeah." at ~0.8 confidence, so
    the duration/transcript-length heuristics remain the primary defense.
  - The `uv`/`VIRTUAL_ENV`/cwd gotcha from the spec: setting `VIRTUAL_ENV` defensively at
    `nala/voice.py`'s import time was sufficient in direct testing (synthesis succeeded from
    a different cwd with `VIRTUAL_ENV` unset too) — no cwd requirement or subprocess
    isolation was needed beyond the MLX thread-pinning fix above.
- **Next (Session 5 / M7):** iOS app (Expo) — push, location, health, voice over the
  `com.nala.tunnel` cloudflared tunnel. Same core, a second client.

## Commands

```bash
.venv/bin/python -m nala.cli               # REPL (typed turns; `transcript`, `confirm <token>`)
.venv/bin/python -m nala.cli --turn "…"    # one-shot
.venv/bin/python -m nala.cli --briefing    # compose + print the morning briefing
.venv/bin/python -m nala.cli --briefing --speak  # also synthesize + afplay it aloud
.venv/bin/python -m nala.scheduler         # watchers + triage, one asyncio loop, runs forever
.venv/bin/python -m nala.serve             # FastAPI feed on 127.0.0.1:8642 (localhost only)
.venv/bin/python -m nala.google_auth       # one-time interactive OAuth flow (run manually, never by a watcher)
.venv/bin/python -m nala.seed_memory       # seed the starter graph (7 projects + 'you') — idempotent
.venv/bin/python scripts/voice_smoke.py    # live smoke test: `say` -> /api/voice/turn -> prints transcript/reply/timing
.venv/bin/pytest -q                        # full suite — must be green before any commit
bash scripts/lint_action_path.sh           # loud-failure lint — no swallowed exceptions
```

## Gotchas

- Python is the **uv-managed 3.12 venv at `.venv`** — never the system 3.14 (audio SDKs at
  M6 require ≤3.12). Install deps with `uv pip install`.
- Secrets live only in `.env` (gitignored, chmod 600). Never in code, commits, or logs.
- Runtime data is `~/.nala/` (events.db WAL, append-only). Tests must set `NALA_DATA_DIR`
  and `NALA_PROJECTS_ROOT` to tmp dirs — never touch real data or real `~/Projects` repos.
- Tests never hit the real backlog on :8421, the real Ollama instance, or the real Google
  API — use the fake-backlog/fake-ollama fixtures in conftest and an injectable
  `service_factory` for gmail/calendar watchers.
- Side effects go through `chokepoint.execute_action` ONLY. Tools raise outside it; keep
  the one-test-per-tool direct-call guard when adding tools.
- The chokepoint guard is a **call-stack-scoped `DispatchTicket`** (`nala/tools/__init__.py`),
  not a contextvar — a contextvar gets copied into any `asyncio.Task` spawned inside a
  dispatch window and keeps the guard "open" in that task forever. Tools receive the ticket
  explicitly via `tools.dispatch(action_type, args, ticket)`; never re-introduce ambient state.
  It guards against *accidental* out-of-chokepoint calls, not malicious in-process code — a
  forgeable capability in a trusted single-user local process, same as the contextvar before it.
- `report_status` is a pure read — it deliberately bypasses the idempotency ledger.
- Rejections (validation/spend) never create `processed_actions` rows.
- Proactive actions (from `nala.triage`) pass `execute_action(..., purpose=...)` — since M5 the
  purpose's risk profile decides the gate (read_only rejects / notify_only → `notified` /
  act_confirm → `awaiting_confirm`), not a blanket `force_confirm`. An unassigned purpose is
  coalesced to a non-None sentinel before reaching `execute_action` (`triage.UNKNOWN_PURPOSE_SENTINEL`)
  so it falls back to `notify_only` — passing bare `None` would be read as "this is a direct user
  turn," skipping gating entirely. `force_confirm` still works for backward compat but nothing
  passes it anymore.
- `confirm_action`/`reject_action`/`dismiss_action` share token resolution (`_find_row_by_status`,
  parameterized by target status) and both hex-validate + Python-match the token — never SQL
  `LIKE` on raw user input. `nala.serve` calls these same functions directly; don't reimplement
  confirm/reject/dismiss logic in the API layer.
- `NALA_OLLAMA_URL` already includes the `/v1` suffix (e.g. `http://localhost:11434/v1`) —
  don't append it again, just `f"{url}/chat/completions"`.
- Watermarks (last-seen cursor per watcher/triage) live in `nala/state.py` (promoted out of
  `nala/watchers/` once triage needed it too) — not watcher-specific despite the historical name.
- `nala.memory` functions (`upsert_node`/`add_edge`/`add_observation`/`delete_node`) have no
  gating or logging of their own — real writes go through `execute_action("memory_write", ...)`
  only. `nala/seed_memory.py` is the one deliberate exception (a one-off bootstrap script, not a
  turn), which is why seeded nodes never show up in `/api/memory/writes` or the feed.
- A `notified` `processed_actions` row means the side effect **never happened** — `dismiss_action`
  is pure bookkeeping, there's nothing to undo. Don't confuse it with `awaiting_confirm`, which
  still dispatches on confirm.
- `nala/purposes.py` deliberately doesn't cache — `load_all()`/`risk_profile_for()` re-read and
  re-validate the YAML on every call. Fine at this scale; don't "optimize" it without checking
  whether tests rely on picking up manifest edits without a process restart.
- **MLX arrays/streams are thread-affine.** Never call `parakeet_mlx`/`mlx_audio` functions from
  an arbitrary thread (e.g. a fresh `asyncio.to_thread` call, which can land on a different pool
  thread each time) — a model loaded on one thread breaks with `RuntimeError: There is no
  Stream(cpu, N) in current thread` the moment a later call lands on another. `nala/voice.py`
  funnels every MLX-touching call (model load, `transcribe()`, `generate_audio()`) through one
  dedicated single-worker `_MLX_EXECUTOR` so it's always the same thread. If you add more
  MLX-backed functionality, route it through that same executor rather than a bare
  `asyncio.to_thread` or a new thread pool.
- `nala/voice.py` sets `VIRTUAL_ENV` defensively at import time (mlx-audio's TTS pipeline has
  been reported to shell out to `uv` on some first-run code paths) — verified sufficient via
  direct testing, no cwd requirement needed on top of it.
- `parakeet_mlx`'s `AlignedResult`/`AlignedSentence` DO expose a real `.confidence` (geometric
  mean of token confidences) — don't assume it's unavailable. It's a secondary signal in
  `voice.gate_low_confidence`, not primary: real testing showed ~200ms of silence can still
  produce a confident-looking hallucinated transcript, so duration/transcript-length checks are
  the primary defense.
- Voice tests never load the real STT/TTS models — `voice._get_stt_model`/`_get_tts_model`/
  `generate_audio` are monkeypatched with fakes throughout `tests/test_voice.py`.

## Session checklist

- [ ] `pytest -q` green, lint script clean
- [ ] Any new tool: chokepoint guard test + loud_failure wrapping + reversibility tag
- [ ] Any new watcher: watermark correctness test (no duplicate signals on re-poll) +
      watcher-failure-is-loud test, wired into `nala/scheduler.py`'s per-watcher loop
- [ ] "in-doubt actions: N" still prints in every status report
- [ ] Update Status section above; push to main

## Related projects

- `~/.backlog/server.py` — task API Nala writes to (no auth, no pagination, TEXT columns)
- `~/.claude-dashboard/parse_usage.py` — cost rates must stay in sync with nala/spend.py
- `mockups/jarvis-final-flow.html` — UX north star (project renamed Jarvis → Nala); also the
  visual reference for `nala/static/index.html`
- Ollama serving `llama3.2:3b` at `NALA_OLLAMA_URL` (OpenAI-compatible `/v1`) — local triage
- Google Cloud OAuth client at `NALA_GOOGLE_CLIENT_SECRET`; token at `~/.nala/google_token.json`
  (chmod 600) — gmail.readonly + calendar.readonly scopes only
