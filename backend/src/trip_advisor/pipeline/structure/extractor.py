"""The LLM boundary. Everything else in this package works on plain dicts and is offline."""

from typing import Any, Protocol

from trip_advisor.pipeline.collect.models import RawDocument

from .prompt import SYSTEM, TOOL_NAME, tool_definition, user_message

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class Extractor(Protocol):
    def extract(self, doc: RawDocument, site_name: str) -> list[dict[str, Any]]:
        """Raw, unvalidated record dicts proposed for this document."""
        ...


class AnthropicExtractor:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, max_tokens: int = 2000) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def extract(self, doc: RawDocument, site_name: str) -> list[dict[str, Any]]:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM,
            tools=[tool_definition()],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": user_message(doc, site_name)}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == TOOL_NAME:
                records = block.input.get("records") if isinstance(block.input, dict) else None
                if not isinstance(records, list):
                    return []
                return [r for r in records if isinstance(r, dict)]
        return []
