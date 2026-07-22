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
- **Next (Session 3 / M5):** graph memory (nodes/edges/observations, provenance,
  confirmable writes) + Relationships/Baby purposes. Per-purpose risk profiles
  (auto/notify/confirm) land here — M4's proactive actions are hardcoded to always
  require confirm regardless of reversibility; that blanket rule should become the
  Projects/Home risk profile once purposes exist, not stay a special case in
  `nala.triage`.

## Commands

```bash
.venv/bin/python -m nala.cli               # REPL (typed turns; `transcript`, `confirm <token>`)
.venv/bin/python -m nala.cli --turn "…"    # one-shot
.venv/bin/python -m nala.cli --briefing    # compose + print the morning briefing
.venv/bin/python -m nala.scheduler         # watchers + triage, one asyncio loop, runs forever
.venv/bin/python -m nala.serve             # FastAPI feed on 127.0.0.1:8642 (localhost only)
.venv/bin/python -m nala.google_auth       # one-time interactive OAuth flow (run manually, never by a watcher)
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
- `report_status` is a pure read — it deliberately bypasses the idempotency ledger.
- Rejections (validation/spend) never create `processed_actions` rows.
- Proactive actions (from `nala.triage`) always call `execute_action(..., force_confirm=True)`
  — every proposal is gated in M4 regardless of the action's own reversibility tag.
- `confirm_action`/`reject_action` share token resolution (`_find_awaiting_confirm_row`) and
  both hex-validate + Python-match the token — never SQL `LIKE` on raw user input. `nala.serve`
  calls these same functions directly; don't reimplement confirm/reject logic in the API layer.
- `NALA_OLLAMA_URL` already includes the `/v1` suffix (e.g. `http://localhost:11434/v1`) —
  don't append it again, just `f"{url}/chat/completions"`.
- Watermarks (last-seen cursor per watcher/triage) live in `nala/state.py` (promoted out of
  `nala/watchers/` once triage needed it too) — not watcher-specific despite the historical name.

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
