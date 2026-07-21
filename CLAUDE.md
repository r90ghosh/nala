# Nala — Project Instructions

Voice-first, proactive, multipurpose personal assistant running locally on the Mac.
**PLAN.md is the authoritative spec** — read its "Reliability spine" section before touching
the action path. Repo: https://github.com/r90ghosh/nala

## Status

- **Session 1 complete (2026-07-21):** M0–M3 spine built, reviewed, hardened. Typed-text
  CLI works end to end against the real backlog (:8421) and real Claude API.
  24 tests green. Commits M0→M3 + review-fix pushed to main.
- **Next (Session 2 / M4):** watchers (gmail, calendar, git) + Ollama triage + morning
  briefing + minimal web UI. Prereqs: Google OAuth creds, `brew install ollama` + pull a
  3B/8B model. **Hard precondition in PLAN.md:** the contextvar chokepoint guard must be
  made call-stack-scoped before any async/threaded watcher code lands.

## Commands

```bash
.venv/bin/python -m nala.cli            # REPL (typed turns; `transcript`, `confirm <token>`)
.venv/bin/python -m nala.cli --turn "…" # one-shot
.venv/bin/pytest -q                     # full suite — must be green before any commit
bash scripts/lint_action_path.sh        # loud-failure lint — no swallowed exceptions
```

## Gotchas

- Python is the **uv-managed 3.12 venv at `.venv`** — never the system 3.14 (audio SDKs at
  M6 require ≤3.12). Install deps with `uv pip install`.
- Secrets live only in `.env` (gitignored, chmod 600). Never in code, commits, or logs.
- Runtime data is `~/.nala/` (events.db WAL, append-only). Tests must set `NALA_DATA_DIR`
  and `NALA_PROJECTS_ROOT` to tmp dirs — never touch real data or real `~/Projects` repos.
- Tests never hit the real backlog on :8421 — use the fake-backlog fixture in conftest.
- Side effects go through `chokepoint.execute_action` ONLY. Tools raise outside it; keep
  the one-test-per-tool direct-call guard when adding tools.
- `report_status` is a pure read — it deliberately bypasses the idempotency ledger.
- Rejections (validation/spend) never create `processed_actions` rows.

## Session checklist

- [ ] `pytest -q` green, lint script clean
- [ ] Any new tool: chokepoint guard test + loud_failure wrapping + reversibility tag
- [ ] "in-doubt actions: N" still prints in every status report
- [ ] Update Status section above; push to main

## Related projects

- `~/.backlog/server.py` — task API Nala writes to (no auth, no pagination, TEXT columns)
- `~/.claude-dashboard/parse_usage.py` — cost rates must stay in sync with nala/spend.py
- `mockups/jarvis-final-flow.html` — UX north star (project renamed Jarvis → Nala)
