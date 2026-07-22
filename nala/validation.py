"""Intent schemas + enum allowlists — the boundary validation the chokepoint
enforces before any tool is dispatched. Out-of-set values are rejected with a
clarifying suggestion, never silently coerced or guessed."""

import difflib
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ValidationError, model_validator


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


class NodeKind(str, Enum):
    person = "person"
    project = "project"
    preference = "preference"
    event = "event"
    thing = "thing"
    place = "place"


class PurposeScope(str, Enum):
    projects = "projects"
    finance = "finance"
    baby = "baby"
    relationships = "relationships"
    home = "home"
    news = "news"
    interests = "interests"
    purchase = "purchase"
    people = "people"  # the shared core — persons live here regardless of which purpose observed them


class ObservationSource(str, Enum):
    user_said = "user_said"
    gmail = "gmail"
    imessage = "imessage"
    calendar = "calendar"
    triage = "triage"
    manual = "manual"


class MemoryOp(str, Enum):
    upsert_node = "upsert_node"
    add_edge = "add_edge"
    add_observation = "add_observation"
    delete_node = "delete_node"


class MemoryWriteIntent(BaseModel):
    """Args shape differs per op — validated by _check_required_fields below
    rather than four separate pydantic models, since op is a single
    discriminator field or none of this reduces to today's simpler intents."""
    action_type: Literal["memory_write"] = "memory_write"
    op: MemoryOp
    kind: NodeKind | None = None
    label: str | None = None
    purpose_scope: PurposeScope | None = None
    src_node: str | None = None
    rel: str | None = None
    dst_node: str | None = None
    node_id: str | None = None
    fact: str | None = None
    source: ObservationSource | None = None
    source_ref: str | None = None

    @model_validator(mode="after")
    def _check_required_fields(self):
        if self.op == MemoryOp.upsert_node:
            missing = [f for f in ("kind", "label", "purpose_scope") if getattr(self, f) is None]
        elif self.op == MemoryOp.add_edge:
            missing = [f for f in ("src_node", "rel", "dst_node") if getattr(self, f) is None]
        elif self.op == MemoryOp.add_observation:
            missing = [f for f in ("fact", "source", "source_ref") if getattr(self, f) is None]
            if self.node_id is None and not (self.kind and self.label and self.purpose_scope):
                missing.append("node_id or (kind, label, purpose_scope)")
        elif self.op == MemoryOp.delete_node:
            missing = [f for f in ("node_id",) if getattr(self, f) is None]
        else:
            missing = []
        if missing:
            raise ValueError(f"memory_write op '{self.op.value}' missing required fields: {missing}")
        return self


class MemoryRecallIntent(BaseModel):
    action_type: Literal["memory_recall"] = "memory_recall"
    label: str | None = None
    kind: NodeKind | None = None
    purpose_scope: PurposeScope | None = None


INTENT_MODELS: dict[str, type[BaseModel]] = {
    "capture_task": CaptureTaskIntent,
    "report_status": ReportStatusIntent,
    "archive_task": ArchiveTaskIntent,
    "memory_write": MemoryWriteIntent,
    "memory_recall": MemoryRecallIntent,
}

REVERSIBILITY: dict[str, str] = {
    "capture_task": "reversible",
    "report_status": "reversible",
    "archive_task": "irreversible",
    "memory_write": "reversible",
    "memory_recall": "reversible",
}

_ENUM_FIELDS: dict[str, type[Enum]] = {
    "project": Project,
    "priority": Priority,
    "category": Category,
    "kind": NodeKind,
    "purpose_scope": PurposeScope,
    "source": ObservationSource,
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
