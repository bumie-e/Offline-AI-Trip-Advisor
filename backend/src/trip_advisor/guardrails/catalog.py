"""What the model was allowed to know: every citable ID with a plain description and its age."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str  # road_note, site_fact, cost_note, weather, event, route
    text: str  # short description, also what number checks compare against
    publisher: str
    as_of: date | None  # publication or forecast date; None when unknown


@dataclass(frozen=True)
class SourceRef:
    """One source line to show under an advice item."""

    id: str
    publisher: str
    as_of: date | None
    age_days: int | None
    text: str

    def label(self) -> str:
        if self.age_days is None:
            return f"{self.publisher}, date unknown"
        when = "today" if self.age_days == 0 else f"{self.age_days} days old"
        return f"{self.publisher}, {self.as_of} ({when})"


@dataclass
class Catalog:
    facts: dict[str, Fact] = field(default_factory=dict)

    def add(self, fact: Fact) -> None:
        self.facts[fact.id] = fact

    @property
    def ids(self) -> set[str]:
        return set(self.facts)

    def sources_for(self, cited_ids: list[str], today: date) -> list[SourceRef]:
        """Sources and their age for the IDs that exist. Unknown IDs are silently skipped."""
        refs = []
        for cid in cited_ids:
            f = self.facts.get(cid)
            if f:
                age = (today - f.as_of).days if f.as_of else None
                refs.append(SourceRef(f.id, f.publisher, f.as_of, age, f.text))
        return refs
