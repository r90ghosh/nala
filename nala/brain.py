"""Hardened LLM wrapper: 30s timeout, 2 retries with backoff (via the
Anthropic SDK's own retry machinery), and a structural check that the model
actually selected a tool. Logs llm_request/llm_response events itself, since
it's the only place with visibility into token usage and the raw response.

Enum/boundary validation of the resulting intent happens downstream, at the
chokepoint (nala.validation) — not here."""

from dataclasses import dataclass

import anthropic

from nala import events
from nala.config import get_anthropic_api_key
from nala.routing import AGENTIC_MODEL
from nala.spend import check_ceiling, record_spend

MODEL = AGENTIC_MODEL
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2

TOOLS_SCHEMA = [
    {
        "name": "capture_task",
        "description": "Capture a new task/todo item into the project backlog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "short task title"},
                "project": {
                    "type": "string",
                    "description": "which project this task belongs to",
                    "enum": [
                        "parentlogs", "life_os", "travel_ai", "hoa-community-platform",
                        "community_portal", "legal-ai-assistant", "last_mile",
                    ],
                },
                "priority": {
                    "type": "string",
                    "description": "task priority",
                    "enum": ["critical", "high", "medium", "low"],
                },
                "category": {
                    "type": "string",
                    "description": "task category",
                    "enum": ["feature", "bug", "improvement", "chore", "idea"],
                },
            },
            "required": ["title", "project"],
        },
    },
    {
        "name": "report_status",
        "description": "Report git status (branch, dirty, ahead/behind) across all tracked project repos.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_write",
        "description": (
            "Record or update something in the personal memory graph. Use op='upsert_node' to "
            "create/update an entity (person/project/preference/event/thing/place); op='add_edge' "
            "to relate two existing entities by node_id; op='add_observation' to record a fact "
            "against a node (pass node_id if it already exists, or kind+label+purpose_scope to "
            "create it in the same call); op='delete_node' to remove an entity entirely. When the "
            "user directly tells you something ('remember that...'), always set source='user_said' "
            "and source_ref to a short quote of what they said — provenance is required, never omit it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": ["upsert_node", "add_edge", "add_observation", "delete_node"],
                },
                "kind": {
                    "type": "string",
                    "enum": ["person", "project", "preference", "event", "thing", "place"],
                },
                "label": {"type": "string", "description": "the entity's name/label"},
                "purpose_scope": {
                    "type": "string",
                    "description": "which purpose this belongs to, or 'people' for persons",
                    "enum": ["projects", "finance", "baby", "relationships", "home", "news", "interests", "purchase", "people"],
                },
                "src_node": {"type": "string", "description": "node_id for add_edge"},
                "rel": {"type": "string", "description": "relationship label for add_edge"},
                "dst_node": {"type": "string", "description": "node_id for add_edge"},
                "node_id": {"type": "string", "description": "existing node_id, for add_observation or delete_node"},
                "fact": {"type": "string", "description": "the fact being recorded, for add_observation"},
                "source": {
                    "type": "string",
                    "enum": ["user_said", "gmail", "imessage", "calendar", "triage", "manual"],
                },
                "source_ref": {"type": "string", "description": "a short reference for where this fact came from"},
            },
            "required": ["op"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Search the personal memory graph for nodes matching a label, kind, and/or purpose_scope.",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["person", "project", "preference", "event", "thing", "place"],
                },
                "purpose_scope": {
                    "type": "string",
                    "enum": ["projects", "finance", "baby", "relationships", "home", "news", "interests", "purchase", "people"],
                },
            },
        },
    },
]


class BrainError(Exception):
    """Raised when the brain cannot produce a usable intent."""


@dataclass
class RawIntent:
    action_type: str
    args: dict


class Brain:
    """Swappable interface: decide(utterance, *, turn_id, session_id) -> RawIntent."""

    def __init__(self, api_key: str | None = None, model: str = MODEL):
        self.client = anthropic.Anthropic(
            api_key=api_key or get_anthropic_api_key(),
            timeout=TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
        )
        self.model = model

    def decide(self, utterance: str, *, turn_id: str, session_id: str, memory_context: str | None = None) -> RawIntent:
        """memory_context: a short slice of the memory graph (nala.cli's
        _memory_context_for_turn), passed as the system prompt so the model
        can reference what it already knows without the caller having to
        splice it into the user turn itself. None when there's nothing
        relevant (or memory is unreachable) — omitted entirely, not sent as
        an empty system prompt."""
        check_ceiling()  # refuse before dispatch, not after paying for the call

        events.log_event(session_id, turn_id, "llm_request", {"utterance": utterance, "model": self.model})

        extra: dict = {"system": memory_context} if memory_context else {}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                tools=TOOLS_SCHEMA,
                messages=[{"role": "user", "content": utterance}],
                **extra,
            )
        except anthropic.APIError as exc:
            raise BrainError(f"brain unreachable: {exc}") from exc

        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        events.log_event(
            session_id, turn_id, "llm_response",
            {
                "tool_name": tool_block.name if tool_block else None,
                "tool_input": tool_block.input if tool_block else None,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            },
        )

        record_spend(
            turn_id=turn_id,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        if tool_block is None:
            raise BrainError("model did not select a tool; cannot form an intent")

        return RawIntent(action_type=tool_block.name, args=tool_block.input)
