"""Intent schemas + enum allowlists — the boundary validation the chokepoint
enforces before any tool is dispatched. Out-of-set values are rejected with a
clarifying suggestion, never silently coerced or guessed."""

import difflib
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ValidationError


class Project(str, Enum):
    parentlogs = "parentlogs"
    life_os = "life_os"
    travel_ai = "travel_ai"
    hoa_community_platform = "hoa-community-platform"
    community_portal = "community_portal"
    legal_ai_assistant = "legal-ai-assistant"
    last_mile = "last_mile"


class Priority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class Category(str, Enum):
    feature = "feature"
    bug = "bug"
    improvement = "improvement"
    chore = "chore"
    idea = "idea"


class CaptureTaskIntent(BaseModel):
    action_type: Literal["capture_task"] = "capture_task"
    title: str
    project: Project
    priority: Priority = Priority.medium
    category: Category = Category.feature


class ReportStatusIntent(BaseModel):
    action_type: Literal["report_status"] = "report_status"


class ArchiveTaskIntent(BaseModel):
    action_type: Literal["archive_task"] = "archive_task"
    task_id: int


INTENT_MODELS: dict[str, type[BaseModel]] = {
    "capture_task": CaptureTaskIntent,
    "report_status": ReportStatusIntent,
    "archive_task": ArchiveTaskIntent,
}

REVERSIBILITY: dict[str, str] = {
    "capture_task": "reversible",
    "report_status": "reversible",
    "archive_task": "irreversible",
}

_ENUM_FIELDS: dict[str, type[Enum]] = {
    "project": Project,
    "priority": Priority,
    "category": Category,
}


class IntentValidationError(Exception):
    def __init__(self, message: str, suggestion: str | None = None):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


def _suggest(value: str, enum_cls: type[Enum]) -> str | None:
    allowed = [e.value for e in enum_cls]
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    for candidate in allowed:
        if candidate.replace("-", "_") == normalized:
            return candidate
    normalized_allowed = {a.replace("-", "_"): a for a in allowed}
    matches = difflib.get_close_matches(normalized, normalized_allowed.keys(), n=1, cutoff=0.6)
    if matches:
        return normalized_allowed[matches[0]]
    return None


def validate_intent(action_type: str, args: dict) -> BaseModel:
    model_cls = INTENT_MODELS.get(action_type)
    if model_cls is None:
        raise IntentValidationError(f"unknown action '{action_type}'")

    try:
        return model_cls(action_type=action_type, **args)
    except ValidationError as exc:
        for err in exc.errors():
            field = err["loc"][0] if err["loc"] else None
            if field in _ENUM_FIELDS and field in args:
                bad_value = args[field]
                suggestion = _suggest(str(bad_value), _ENUM_FIELDS[field])
                msg = f"unknown {field} '{bad_value}'"
                raise IntentValidationError(msg, suggestion) from exc
        raise IntentValidationError(f"invalid intent for '{action_type}': {exc}") from exc
