"""Model routing policy — task class to model. This is the single source of
truth: nala.brain, nala.triage, and nala.briefing import their model
constant from here, and the web UI's Model Router panel reads the same
ROUTES table via GET /api/routing. Neither side can drift from the other —
there's only one place a routing change is ever made."""

TRIAGE_MODEL = "llama3.2:3b"
BRIEFING_MODEL = "claude-sonnet-5"
AGENTIC_MODEL = "claude-sonnet-5"  # brain.py's tool-calling model

ROUTES = [
    {"task": "triage", "model": TRIAGE_MODEL, "tier": "local", "cost_note": "$0"},
    {"task": "briefing", "model": BRIEFING_MODEL, "tier": "cloud", "cost_note": ""},
    {"task": "agentic", "model": AGENTIC_MODEL, "tier": "cloud", "cost_note": ""},
]


def get_routes() -> list[dict]:
    return ROUTES
