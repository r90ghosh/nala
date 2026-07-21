# Nala — Complete Build Plan

Voice-first, proactive, multipurpose personal assistant. Runs entirely on Ashirbad's Mac
(M4 Pro, 24GB) as a local service; iPhone connects over a cloudflared tunnel. No cloud
hosting, no Netlify, no Supabase. Repo: https://github.com/r90ghosh/nala

## Locked decisions

- **Voice-first** (push-to-talk Mac + iOS), but the spine is built and proven **text-first**.
- **Multipurpose from day one** (architecture-wise): Projects · Finance · Baby · Relationships
  · Home · News · Interests · Purchase — each a manifest folder, added incrementally.
- **Proactive agent**: watchers → signals → triage → proposals, gated by per-purpose risk
  profiles. Delivery: iPhone push + daily spoken briefing.
- **Custom pipeline** (no agent framework): provider adapters (anthropic / openai-compatible
  / gemini) behind one interface; Ollama for local models; BYOK for cloud.
- **Graph memory**: SQLite nodes/edges/observations, per-purpose scope + shared `people`
  core; every fact has provenance; every write is a confirmable event.
- **Reliability spine is non-negotiable** (usefulness first, spine as hard requirement):
  single chokepoint, idempotency, two-phase writes, reconciler, four-clause loud failure,
  boundary validation, confirm-gating, spend ceiling.

## Architecture

```
┌─ WATCHERS (pollers) ────────────────────────────────────────────┐
│ gmail · calendar · imessage · git/gh/netlify · simplefin · news │
│ location/health (posted in by iOS app)                          │
└──────────────┬──────────────────────────────────────────────────┘
               ▼  normalized SIGNAL events → events.db (append-only, WAL)
        ┌─ TRIAGE (cheap/local model) ─┐
        │ ignore | remember | propose  │
        └──────────────┬───────────────┘
                       ▼
        ┌─ execute_action(intent) — THE CHOKEPOINT ──────┐
        │ idempotency · validation · spend ceiling ·     │
        │ risk profile: auto(read) / notify / confirm    │
        └──────┬─────────────────────────────────────────┘
               ▼
  actions · memory writes · deliveries (push / briefing / feed)
```

Turns are transport-agnostic: typed text (M0+) or LiveKit-audio→STT (M6+). The core never
knows which. Runtime data lives in `~/.nala/` (events.db, memory.db, logs).

## Reliability spine (the contract — applies to every action, reactive or proactive)

1. **Single chokepoint.** Tools are dispatched only by `execute_action(intent)`. Each tool
   raises if invoked outside it (assert: live txn + `pending` idempotency row). One test per
   tool asserts a direct call throws.
2. **Idempotency.** `key = sha256(action_type + canonical_json(args) + turn_id)`.
   `processed_actions(idempotency_key PK, turn_id, action_type, reversibility, args_json,
   status, result_json, error_json, created_at, resolved_at)`,
   `status ∈ {pending, done, failed, rejected, awaiting_confirm}`. INSERT-or-ignore before
   the side effect; terminal key returns stored result, never re-runs.
3. **Atomicity + reconciliation.** Two-phase: commit `pending` → side effect → terminal
   state. Rows still `pending` at startup = **in-doubt**; the reconciler resolves them
   against the source of truth (`GET :8421/api/tasks`). "in-doubt actions: N" is a permanent
   line in every status report.
4. **Loud failure (all four clauses).** (a) spoken/printed in the same turn; (b) logged with
   cause as `events` row `level='error'`; (c) no silent-proceed on low STT confidence or
   schema-invalid intent — ask, don't guess; (d) every action reaches a terminal state or
   that absence is itself a surfaced error. Bare `except` / swallow patterns banned in the
   action path (lint rule).
5. **Boundary validation.** Intent validated at the chokepoint against real enums:
   project ∈ {parentlogs, life_os, travel_ai, hoa-community-platform, community_portal,
   legal-ai-assistant, last_mile}, priority ∈ {critical, high, medium, low},
   category ∈ {feature, bug, improvement, chore, idea}. Out-of-set → rejected + clarify.
6. **Confirm-gating.** Every action tagged `reversibility ∈ {reversible, irreversible}`.
   Irreversible actions require a non-voice confirm (typed token / tap). Ships from M3 with
   one stubbed irreversible action (`archive_task`) so the gate is on the live path early.
7. **Spend ceiling.** `spend(ts, turn_id, model, input_tokens, output_tokens, est_cost_usd,
   day)`; per-day ceiling checked in the chokepoint precondition block. Tier slider honored
   literally; "bump tier?" is surfaced, never auto-escalated.

## Model registry & router

`~/.nala/models.yaml` — providers (adapter + key ref + base_url) and models (id, tier,
capability flags, cost rates). Three adapters cover everything: `anthropic`,
`openai-compatible` (Ollama/OpenAI/Moonshot/OpenRouter/Groq), `gemini`. Ollama models
auto-discovered via `/api/tags`. New models get a **probe** (streaming? tool-calling?
structured output?) and the router refuses to send agentic work to models that failed the
tool probe. Routing policy: task class → model (triage→local, briefing→mid, agentic→top),
overridable per purpose. Default tiers at build time: cheap=claude-haiku-4-5,
moderate=claude-sonnet-5, expensive=claude-opus-4-8.

## Purposes (manifest folders, added over sessions)

`purposes/<name>/manifest.yaml`: watchers used, tools allowed, risk profile, memory scope,
briefing sections, default tier. Risk profiles: Projects/Home = act+confirm,
Finance/News/Interests/Purchase = read-only, Relationships/Baby = notify-only.

## Data access (confirmed feasible)

- **Official APIs:** Gmail, Google Calendar (OAuth); web search; gh/netlify CLIs.
- **Mac-local (Full Disk Access):** iMessage `chat.db` (read), call-history metadata,
  Notes, browser history, Photos metadata. iMessage **send** via AppleScript = gated action.
- **iOS app:** geolocation (significant-change), HealthKit, push (APNs).
- **Finance:** SimpleFIN Bridge (~$1.50/mo) or CSV drop-folder. Read-only.
- **Skip:** Find My scraping, WhatsApp bridges, call audio (impossible).

## Voice (M6+)

LiveKit (Cloud) transport; streaming STT = ElevenLabs Scribe v2 RT (default) or Deepgram
Flux; TTS = Cartesia Sonic (system `say` acceptable pre-polish). Pipeline, not
speech-to-speech — the brain and dispatch stay in our code.

## Clients

- **Mac:** local web UI served by the agent (FastAPI + static/Next), Mission Control layout:
  Triptych home (status+memory / observability feed / actions+models), Chat canvas, Memory
  graph tab. Reference mockup: `mockups/jarvis-final-flow.html`.
- **iOS:** Expo custom dev client — push-to-talk, swipe-to-confirm, briefing playback,
  location/health reporters. Connects via cloned cloudflared tunnel (`com.nala.tunnel`).

## Repo structure

```
nala/
  PLAN.md  README.md  .env(.gitignored)  pyproject.toml  .venv/
  nala/
    __init__.py  config.py
    events.py        # append-only event log (~/.nala/events.db, WAL)
    brain.py         # hardened LLM wrapper: retry, timeout, schema-validated intent
    chokepoint.py    # execute_action — idempotency, validation, spend, confirm-gating
    validation.py    # intent schemas + enum allowlists
    reconciler.py    # startup + pre-status in-doubt resolution
    spend.py         # ledger + daily ceiling
    tools/
      __init__.py    # registry; tools raise outside chokepoint
      report_status.py  capture_task.py  archive_task.py(stub, irreversible)
    cli.py           # typed-text REPL: turn in → transcript rendering out
  tests/             # pytest; fake backlog server fixture; never hits real :8421
  mockups/           # design artifacts (historical, kept)
```

## Milestones

| # | Builds | Adds (the lesson) | Session |
|---|--------|-------------------|---------|
| M0 | Naive baseline: CLI, `capture_task` POSTs :8421, `report_status` shells git/gh | control group — deliberately naive | 1 |
| M1 | `events.db` append-only log; everything routed through it; transcript view | observability: nothing happens off-log | 1 |
| M2 | `execute_action` chokepoint; tools raise outside it; schema+enum validation at boundary | no unwired path; boundary-deep validation | 1 |
| M3 | `processed_actions`, idempotency keys, two-phase writes, startup reconciler, confirm-gate stub, spend ledger + ceiling | idempotent retryable writes, reconciled; gate + budget live | 1 |
| M4 | Watchers (gmail, calendar, git) + Ollama triage + morning briefing (text) + minimal web UI (feed) | proactivity through the same chokepoint | 2 |
| M5 | Graph memory (nodes/edges/observations, provenance, confirmable writes) + Relationships/Baby purposes | memory as gated writes | 3 |
| M6 | Voice on Mac: LiveKit + Scribe/Flux STT + Cartesia TTS; low-confidence → ask | loud failure at the perception boundary | 4 |
| M7 | iOS app (Expo): push, location, health, voice over tunnel `com.nala.tunnel` | same core, two clients | 5 |
| M8 | Finance (SimpleFIN read-only), News/Purchase watchers, digests | thin purposes ride existing rails | 6 |
| M9 | First gated real-world actions: send iMessage, create calendar event | irreversibility guard, for real | 6+ |

**M4 precondition:** the chokepoint's dispatch guard (`nala/tools/__init__.py`) is a
`contextvars.ContextVar` set for the duration of `execute_action()`'s `with
tools.dispatching():` block. That's safe for the current synchronous, single-turn-at-a-time
CLI, but it is **not** concurrency-safe: an `asyncio.create_task(...)` started from inside a
`dispatching()` window inherits the context and keeps the guard open indefinitely in the
child task, and a threaded watcher calling into a tool from a different thread doesn't share
the contextvar at all (so a legitimate dispatch from a watcher thread could wrongly raise
`ToolInvokedOutsideChokepoint`). M4 adds watchers (pollers) and thus real concurrency — the
guard must be made call-stack-scoped (e.g., an explicit token/frame check, or re-deriving the
contextvar per task at spawn time) before any watcher lands. No code change yet; this is a
blocker to resolve as part of M4, not before it.

## Verification (Session 1 gate — all must pass before M3 is "done")

- **Idempotency:** same capture turn twice → exactly one task at backlog; second returns
  stored result; one `processed_actions` row.
- **Atomicity/in-doubt:** kill process between `pending` commit and POST → restart →
  reconciler resolves against `GET /api/tasks` (landed→done; not→failed, loudly).
- **Loud failure:** backlog stopped → capture → printed failure + `level='error'` event
  row; never silent success. Wrong port → status report says "in-doubt actions: N" and
  names the failure; never "all clear".
- **Boundary:** project "last mile" → rejected + clarify, no POST.
- **Chokepoint:** direct tool call (outside `execute_action`) raises — one test per tool.
- **Confirm-gate:** `archive_task` refused without typed confirm.
- **Spend:** ceiling set to $0.01 → next LLM call refused pre-dispatch with reason.

## Prerequisites by session

- **S1 (now):** git repo ✓ · uv venv Python 3.12 ✓ · ANTHROPIC_API_KEY in `.env` ✓ ·
  backlog server at :8421 ✓. Nothing else.
- **S2:** Google Cloud OAuth creds (Gmail+Calendar), `brew install ollama` + pull a 3B/8B.
- **S3:** Full Disk Access for iMessage reads.
- **S4:** ElevenLabs or Deepgram key, Cartesia key, LiveKit Cloud project.
- **S5:** Apple dev account (have), clone tunnel plist.
- **S6:** SimpleFIN Bridge token (verify bank coverage first).

## Conventions

Conventional Commits; one commit per milestone minimum; push to `main`. Tests colocated in
`tests/`, run with `.venv/bin/pytest`; tests use a fake backlog HTTP fixture, never the
real `:8421`. Secrets only in `.env` (gitignored) — never in code, never in commits, never
echoed into logs. Costs computed from registry rates; keep in sync with
`~/.claude-dashboard/parse_usage.py`.
