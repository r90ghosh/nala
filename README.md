# Nala

Voice-first, proactive, multipurpose personal assistant that runs entirely on my Mac.
iPhone connects over a private tunnel. Local models via Ollama for high-frequency triage;
cloud models (Claude, Gemini, Kimi, DeepSeek) via BYOK APIs for the heavy lifting.

Built on a hard reliability spine: single action chokepoint, idempotent writes,
reconciliation, loud failure, confirm-gating, and a literal daily spend ceiling.

- **Plan:** [PLAN.md](PLAN.md)
- **UX reference:** `mockups/jarvis-final-flow.html` (project was renamed Jarvis → Nala)
- **Runtime data:** `~/.nala/` (append-only `events.db` is the observability spine)

## Dev

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
cp .env.example .env   # add your keys
.venv/bin/python -m nala.cli   # typed-text REPL (M0–M3)
.venv/bin/pytest
```
