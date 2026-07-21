"""Minimal LLM wrapper: decides which of the two known tools to run and
extracts its arguments via Anthropic tool-calling. No retries, no timeout
handling, no schema validation — hardened in M2."""

import anthropic

from nala.config import get_anthropic_api_key

MODEL = "claude-sonnet-5"

TOOLS_SCHEMA = [
    {
        "name": "capture_task",
        "description": "Capture a new task/todo item into the project backlog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "short task title"},
                "project": {"type": "string", "description": "which project this task belongs to"},
                "priority": {"type": "string", "description": "critical, high, medium, or low"},
                "category": {"type": "string", "description": "feature, bug, improvement, chore, or idea"},
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


class Brain:
    def __init__(self, api_key: str | None = None, model: str = MODEL):
        self.client = anthropic.Anthropic(api_key=api_key or get_anthropic_api_key())
        self.model = model

    def decide(self, utterance: str):
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=TOOLS_SCHEMA,
            messages=[{"role": "user", "content": utterance}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.name, block.input
        return None, None
