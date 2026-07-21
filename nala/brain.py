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

MODEL = "claude-sonnet-5"
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

    def decide(self, utterance: str, *, turn_id: str, session_id: str) -> RawIntent:
        events.log_event(session_id, turn_id, "llm_request", {"utterance": utterance, "model": self.model})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                tools=TOOLS_SCHEMA,
                messages=[{"role": "user", "content": utterance}],
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

        if tool_block is None:
            raise BrainError("model did not select a tool; cannot form an intent")

        return RawIntent(action_type=tool_block.name, args=tool_block.input)
