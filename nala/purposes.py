"""Loads and validates purposes/<name>/manifest.yaml for all 8 purposes at
startup. A missing or malformed manifest is a loud startup failure — never
a silent skip, since a broken manifest means we genuinely don't know that
purpose's risk profile, and guessing there would be exactly the kind of
silent-proceed the reliability spine bans. Manifests are read fresh on every
call rather than cached: they're tiny, local files, read at most once per
dispatch, and staleness bugs aren't worth the complexity of a cache here."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError, field_validator

PURPOSES_DIR = Path(__file__).resolve().parent.parent / "purposes"

VALID_RISK_PROFILES = {"act_confirm", "notify_only", "read_only"}
VALID_PURPOSE_NAMES = {
    "projects", "finance", "baby", "relationships",
    "home", "news", "interests", "purchase",
}


class PurposeManifestError(Exception):
    """A purpose manifest is missing, malformed, or fails validation."""


class PurposeManifest(BaseModel):
    display_name: str
    risk_profile: str
    watchers: list[str] = []
    tools_allowed: list[str] = []
    memory_scope: str
    briefing_sections: list[str] = []
    default_tier: str

    @field_validator("risk_profile")
    @classmethod
    def _validate_risk_profile(cls, v):
        if v not in VALID_RISK_PROFILES:
            raise ValueError(f"unknown risk_profile '{v}' — must be one of {sorted(VALID_RISK_PROFILES)}")
        return v


def load_all(purposes_dir: Path | None = None) -> dict[str, PurposeManifest]:
    d = purposes_dir or PURPOSES_DIR
    manifests: dict[str, PurposeManifest] = {}
    for name in sorted(VALID_PURPOSE_NAMES):
        path = d / name / "manifest.yaml"
        if not path.exists():
            raise PurposeManifestError(f"missing manifest for purpose '{name}': {path}")
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise PurposeManifestError(f"malformed YAML in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise PurposeManifestError(f"manifest for purpose '{name}' must be a YAML mapping: {path}")
        try:
            manifests[name] = PurposeManifest(**raw)
        except ValidationError as exc:
            raise PurposeManifestError(f"invalid manifest for purpose '{name}' ({path}): {exc}") from exc
    return manifests


def risk_profile_for(purpose: str, purposes_dir: Path | None = None) -> str | None:
    """None if `purpose` isn't one of the 8 known names at all — the caller
    (chokepoint) treats an unrecognized purpose the same as notify_only:
    never guess a stranger purpose into act_confirm or read_only."""
    manifests = load_all(purposes_dir)
    manifest = manifests.get(purpose)
    return manifest.risk_profile if manifest else None
