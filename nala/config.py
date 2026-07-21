"""Runtime configuration, loaded fresh from the environment on every call.

Values are read lazily (not cached at import time) so tests can monkeypatch
env vars per-test — in particular NALA_DATA_DIR, which tests MUST override to
point at a tmp dir rather than the real ~/.nala/.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECTS = [
    "parentlogs",
    "life_os",
    "travel_ai",
    "hoa-community-platform",
    "community_portal",
    "legal-ai-assistant",
    "last_mile",
]


def get_anthropic_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def get_backlog_url() -> str:
    return os.environ.get("NALA_BACKLOG_URL", "http://127.0.0.1:8421")


def get_daily_ceiling() -> float:
    return float(os.environ.get("NALA_DAILY_CEILING_USD", "5.00"))


def get_data_dir() -> Path:
    d = Path(os.environ.get("NALA_DATA_DIR", "~/.nala")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_projects_root() -> Path:
    return Path(os.environ.get("NALA_PROJECTS_ROOT", "~/Projects")).expanduser()
