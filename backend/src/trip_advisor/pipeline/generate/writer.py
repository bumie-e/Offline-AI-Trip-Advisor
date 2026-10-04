"""The LLM boundary for itinerary generation. Everything else here is deterministic."""

from typing import Protocol

from pydantic import Field

from trip_advisor.schemas.common import Strict
from trip_advisor.schemas.itinerary import Advice, Verdict

from .evidence import GenInput
from .rules import Assessment

TOOL_NAME = "write_itinerary"
DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM = f"""You write travel advice for a visitor to a Nigerian heritage site. You are given an \
evidence block and the findings of a rule check.

Rules:
- Reply by calling the {TOOL_NAME} tool, and nothing else.
- Use ONLY the evidence block. Do not add facts, places, prices, times or road conditions.
- Cite with `cited_ids`, using ONLY IDs shown in [brackets] in the evidence. Never invent an ID.
- Wording is advisory: "reports suggest", "may", "consider". Never say a road, place or trip is \
safe or unsafe, and never promise conditions.
- `summary`: two or three sentences giving the overall picture for this trip: the verdict, the \
main reasons (weather forecast, news, road reports) and what the traveller should do. It must agree \
with your reasons, add no new facts, and cite nothing that your reasons do not.
- Every rule finding must be reflected, at no lower severity than the rule check gave it.
- Severity: none, elevated, high. Verdict: go, go_with_changes, not_advised.
- Each reason is one or two short sentences a tired traveller can read quickly. Mention the age of \
the source when you cite a dated record.
- `alternatives` are short actions (leave earlier, other dates, an alternative route from the \
evidence). Do not suggest a mode of travel the evidence does not cover.
- `stop_notes`: the advice a traveller sees on tapping a stop. The outline lists each outbound \
stop with its road and the ids of recent road evidence for it. For every stop that has such ids, \
write one practical sentence for that stop using only that evidence (what the road is like and \
what to do about it), and cite those ids. Skip a stop whose evidence is "none". The note after \
"applies" says how far a report reaches: "here" means it names this place; "road" means it is \
about this road; "corridor" means it is about a wider road that passes this stop, so say it was \
reported on that road and never that it happened at this stop. Use the stop's order number. Every note must list the `cited_ids` it rests on; a note with none is dropped."""


class StopNote(Strict):
    order: int = Field(ge=1)
    note: str = Field(max_length=300)
    cited_ids: list[str] = Field(default_factory=list)  # required for any figure in the note


class WriterOutput(Strict):
    verdict: Verdict
    summary: str = Field(default="", max_length=600)
    verdict_reasons: list[Advice]
    stop_notes: list[StopNote] = Field(default_factory=list)


class ItineraryWriter(Protocol):
    def write(self, inp: GenInput, findings: Assessment, outline: str) -> WriterOutput | None:
        """None when the model produced nothing usable."""
        ...


def user_message(inp: GenInput, findings: Assessment, outline: str) -> str:
    rule_lines = "\n".join(
        f"- {a.severity}: {a.advice} (cites {a.cited_ids})" for a in findings.advice
    )
    return (
        f"<evidence>\n{inp.render()}\n</evidence>\n\n"
        f"<outline>\n{outline}\n</outline>\n\n"
        f'<rule_findings verdict_floor="{findings.verdict}">\n{rule_lines or "- none"}\n'
        "</rule_findings>"
    )


class AnthropicWriter:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, max_tokens: int = 3000) -> None:
        import anthropic

        # A web request has a hard time limit, so fail fast and fall back to the rule text.
        self._client = anthropic.Anthropic(api_key=api_key, timeout=40.0, max_retries=1)
        self.model = model
        self.max_tokens = max_tokens

    def write(self, inp: GenInput, findings: Assessment, outline: str) -> WriterOutput | None:
        from anthropic.types import ToolParam
        from pydantic import ValidationError

        tool: ToolParam = {
            "name": TOOL_NAME,
            "description": "Return the verdict, reasons and stop notes.",
            "input_schema": WriterOutput.model_json_schema(),
        }
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM,
            tools=[tool],
            tool_choice={"type": "auto"},  # newer models reject a forced tool
            messages=[{"role": "user", "content": user_message(inp, findings, outline)}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == TOOL_NAME:
                try:
                    return WriterOutput.model_validate(block.input)
                except ValidationError:
                    return None
        return None
