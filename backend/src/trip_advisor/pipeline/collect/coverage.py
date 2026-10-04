"""Is the collected data enough to describe the road to a site and its current state?"""

from datetime import date

from pydantic import Field

from trip_advisor.schemas.common import Strict

from .models import CorridorEvidence, RawDocument, SiteRoutes

MIN_TOWNS = 2
MIN_FUEL = 1


class CorridorCoverage(Strict):
    corridor: str
    primary: bool
    fresh_items: int
    newest: date | None
    age_days: int | None
    newest_title: str | None


class SiteCoverage(Strict):
    site_id: str
    routes: int
    alternatives: int
    towns_on_primary: int
    fuel_on_primary: int
    guide_pages: int
    corridors: list[CorridorCoverage]
    sufficient: bool
    gaps: list[str]
    run_errors: list[str] = Field(default_factory=list)  # failures from the collection run


def _blocks(gap: str) -> bool:
    """Only gaps in what the traveller needs block 'sufficient'. The rest stay as warnings."""
    if gap.startswith("no road-state report"):
        return "primary corridor" in gap
    if gap.startswith("stops incomplete on route"):
        return gap.startswith("stops incomplete on route primary")
    # A source that failed (serp, news, notices, guides) only matters if it left a blocking
    # gap above; the evidence itself is checked separately.
    return not (" failed" in gap)


def assess(
    site_id: str,
    routes: SiteRoutes | None,
    guides: list[RawDocument],
    evidence: list[CorridorEvidence],
    primary_corridors: set[str],
    today: date,
    errors: list[str],
) -> SiteCoverage:
    gaps = list(errors)
    n_routes = len(routes.routes) if routes else 0
    primary_stops = [s for s in routes.stops if s.route_id == "primary"] if routes else []
    towns = sum(1 for s in primary_stops if s.kind in ("city", "town"))
    fuel = sum(1 for s in primary_stops if s.kind == "fuel")

    if n_routes == 0:
        gaps.append("no route found")
    if n_routes < 2:
        gaps.append("no alternative road found")
    if towns < MIN_TOWNS:
        gaps.append(f"fewer than {MIN_TOWNS} towns on the primary route")
    if fuel < MIN_FUEL:
        gaps.append("no fuel stop on the primary route")

    corridors = []
    for ev in evidence:
        sel = ev.selected
        corridors.append(
            CorridorCoverage(
                corridor=ev.corridor,
                primary=ev.corridor in primary_corridors,
                fresh_items=(1 if sel else 0) + len(ev.others),
                newest=sel.published if sel else None,
                age_days=(today - sel.published).days if sel and sel.published else None,
                newest_title=sel.title if sel else None,
            )
        )
        if sel is None:
            tag = "primary corridor" if ev.corridor in primary_corridors else "corridor"
            weaker = f" ({len(ev.others)} traffic-only items)" if ev.others else ""
            gaps.append(
                f"no road-state report in the last 3 months for {tag} {ev.corridor!r}{weaker}"
            )

    blocking = [g for g in gaps if _blocks(g)]
    return SiteCoverage(
        site_id=site_id,
        routes=n_routes,
        alternatives=max(n_routes - 1, 0),
        towns_on_primary=towns,
        fuel_on_primary=fuel,
        guide_pages=len(guides),
        corridors=corridors,
        sufficient=not blocking,
        gaps=gaps,
        run_errors=errors,
    )
