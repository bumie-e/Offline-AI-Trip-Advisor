"""Check model output against what it was given, and replace what fails.

Applies to the server-side writer and to the on-device model alike: both produce `Advice`.
Principle: a failed line is replaced, never silently dropped, and the warning level is kept,
so a guardrail can make advice plainer but cannot make it more relaxed.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from trip_advisor.schemas.itinerary import Advice, Severity

from .catalog import Catalog
from .wording import wording_problems

MAX_ADVICE_CHARS = 600


class ViolationKind(StrEnum):
    UNKNOWN_ID = "unknown_id"
    UNCITED = "uncited"  # a warning with no source behind it
    WORDING = "wording"
    NUMBER_NOT_IN_SOURCE = "number_not_in_source"
    EMPTY = "empty"
    TOO_LONG = "too_long"


@dataclass(frozen=True)
class Violation:
    kind: ViolationKind
    detail: str
    where: str = ""  # e.g. "reason 2", "stop 1"


_PERCENT = re.compile(r"(\d{1,3})\s?%")


def check_text(text: str, cited_ids: list[str], catalog: Catalog) -> list[Violation]:
    out = [Violation(ViolationKind.UNKNOWN_ID, i) for i in cited_ids if i not in catalog.ids]
    out += [Violation(ViolationKind.WORDING, why) for why in wording_problems(text)]
    # A percentage must come from a cited source, or the model has made up a number.
    cited_text = " ".join(catalog.facts[i].text for i in cited_ids if i in catalog.ids)
    cited_pcts = set(_PERCENT.findall(cited_text))
    out += [
        Violation(ViolationKind.NUMBER_NOT_IN_SOURCE, f"{n}%")
        for n in _PERCENT.findall(text)
        if n not in cited_pcts
    ]
    return out


def check_advice(advice: Advice, catalog: Catalog) -> list[Violation]:
    out = check_text(advice.advice, advice.cited_ids, catalog)
    if not advice.advice.strip():
        out.append(Violation(ViolationKind.EMPTY, "advice text"))
    if len(advice.advice) > MAX_ADVICE_CHARS:
        out.append(Violation(ViolationKind.TOO_LONG, str(len(advice.advice))))
    for alt in advice.alternatives:
        out += [
            Violation(ViolationKind.WORDING, f"alternative: {w}") for w in wording_problems(alt)
        ]
    valid = [i for i in advice.cited_ids if i in catalog.ids]
    if (advice.changed or advice.severity != Severity.NONE) and not valid:
        out.append(Violation(ViolationKind.UNCITED, "warning cites no known source"))
    return out


def template_advice(advice: Advice, catalog: Catalog) -> Advice:
    """A plain sentence built only from the valid sources the advice cited. Keeps its severity."""
    valid = [i for i in advice.cited_ids if i in catalog.ids]
    basis = "; ".join(catalog.facts[i].text.rstrip(".") for i in valid[:3])
    if not valid:
        text = (
            "Something may have changed, but it could not be tied to a source. "
            "Confirm locally before relying on this plan."
            if advice.severity != Severity.NONE
            else "No change was found in the stored information."
        )
    elif advice.severity == Severity.HIGH:
        text = (
            f"Reports suggest conditions may be difficult. Based on: {basis}. Consider other dates."
        )
    elif advice.severity == Severity.ELEVATED:
        text = f"Reports suggest allowing extra time or keeping plans flexible. Based on: {basis}."
    else:
        text = f"No change found. Based on: {basis}."
    return Advice(
        changed=advice.changed,
        severity=advice.severity,
        advice=text,
        alternatives=[a for a in advice.alternatives if not wording_problems(a)],
        cited_ids=valid,
    )


@dataclass
class Guarded:
    advice: Advice
    violations: list[Violation]
    replaced: bool


def guard_advice(advice: Advice, catalog: Catalog) -> Guarded:
    """Pass through if clean, else replace with a template sentence."""
    violations = check_advice(advice, catalog)
    if not violations:
        return Guarded(advice, [], False)
    return Guarded(template_advice(advice, catalog), violations, True)


def guard_note(note: str, cited_ids: list[str], catalog: Catalog) -> tuple[bool, list[Violation]]:
    """(ok, violations) for a free-text note such as a stop note. Failed notes are dropped."""
    violations = check_text(note, cited_ids, catalog)
    return (not violations, violations)
