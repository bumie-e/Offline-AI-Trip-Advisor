"""Everything the generator may know, and the IDs it may cite."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from trip_advisor.guardrails.catalog import Catalog, Fact
from trip_advisor.pipeline.collect.models import RouteOption, SiteRoutes
from trip_advisor.schemas.delta import Delta
from trip_advisor.schemas.itinerary import TripRequest
from trip_advisor.schemas.pack import ImageRecord, PackRecord, RoadNote, SiteFact
from trip_advisor.sites import SiteConfig


def weather_id(day: date) -> str:
    return f"weather-{day.isoformat()}"


def route_id(site_id: str, route: RouteOption) -> str:
    return f"route-{site_id}-{route.id}"


@dataclass
class GenInput:
    site: SiteConfig
    request: TripRequest
    routes: SiteRoutes | None
    records: list[PackRecord]
    delta: Delta
    today: date
    notes: list[str] = field(default_factory=list)  # data gaps worth telling the reader

    @property
    def trip_days(self) -> list[date]:
        n = (self.request.end_date - self.request.start_date).days
        return [self.request.start_date + timedelta(days=i) for i in range(max(n, 0) + 1)]

    @property
    def primary(self) -> RouteOption | None:
        if not self.routes or not self.routes.routes:
            return None
        return next((r for r in self.routes.routes if r.kind == "primary"), self.routes.routes[0])

    @property
    def images(self) -> list[ImageRecord]:
        return [r for r in self.records if isinstance(r, ImageRecord)]

    @property
    def road_notes(self) -> list[RoadNote]:
        return [r for r in self.records if isinstance(r, RoadNote)]

    @property
    def site_facts(self) -> list[SiteFact]:
        return [r for r in self.records if isinstance(r, SiteFact)]

    def known_ids(self) -> set[str]:
        ids = {r.id for r in self.records}
        ids |= {weather_id(w.date) for w in self.delta.weather}
        ids |= {e.source_id for e in self.delta.events}
        if self.routes:
            ids |= {route_id(self.site.id, r) for r in self.routes.routes}
        return ids

    def catalog(self) -> Catalog:
        """The same IDs as `known_ids`, with descriptions and ages for the guardrails."""
        cat = Catalog()
        for r in self.records:
            cat.add(Fact(r.id, r.type, r.summary, r.source.publisher, r.source.published))
        for w in self.delta.weather:
            text = f"Rain chance {w.rain_probability:.0%} on {w.date:%d %b} in {w.area}"
            cat.add(Fact(weather_id(w.date), "weather", text, "Open-Meteo forecast",
                         self.delta.generated_at.date()))  # fmt: skip
        for e in self.delta.events:
            text = f"{e.type} ({e.status}) affecting {', '.join(e.affects)}"
            src = e.source
            cat.add(
                Fact(
                    e.source_id, "event", text,
                    src.publisher if src else "News reports", src.published if src else None,
                )
            )  # fmt: skip
        for rt in self.routes.routes if self.routes else []:
            text = f"{rt.label}: {rt.distance_km:.0f} km, about {rt.duration_min:.0f} min"
            cat.add(Fact(route_id(self.site.id, rt), "route", text, "OpenStreetMap routing",
                         self.routes.collected_at.date()))  # type: ignore[union-attr]  # fmt: skip
        return cat

    def render(self) -> str:
        """The evidence block shown to the model. IDs in [brackets] are the only citable ones."""
        lines = [
            f"Site: {self.site.name}, {self.site.city}, {self.site.state} State",
            f"Trip: {self.request.start_date} to {self.request.end_date}, "
            f"{self.request.group_size} traveller(s), from {self.request.start_city}"
            + (f" via {self.request.arrival_airport}" if self.request.arrival_airport else ""),
            f"Today: {self.today}",
            "",
            "Routes:",
        ]
        for r in self.routes.routes if self.routes else []:
            roads = ", ".join(r.roads) or "unnamed roads"
            lines.append(
                f"- [{route_id(self.site.id, r)}] {r.label}: {r.distance_km:.0f} km, "
                f"~{r.duration_min:.0f} min free-flow, via {roads}"
            )
        lines += ["", "Records:"]
        for rec in self.records:
            when = rec.source.published or "undated"
            lines.append(
                f"- [{rec.id}] ({rec.type}, {rec.confidence} confidence, {rec.source.publisher}, "
                f"{when}) {rec.summary}"
                + (
                    f" Rain sensitivity: {rec.rain_sensitivity}."
                    if isinstance(rec, RoadNote)
                    else ""
                )
            )
        lines += ["", "Weather forecast (chance of rain):"]
        for w in self.delta.weather:
            lines.append(f"- [{weather_id(w.date)}] {w.date} {w.area}: {w.rain_probability:.0%}")
        lines += ["", "Disruption news:"]
        for e in self.delta.events:
            span = f" {e.start or '?'} to {e.end or '?'}" if e.start or e.end else ", dates unknown"
            by = f" Source: {e.source.publisher}, {e.source.published}." if e.source else ""
            lines.append(
                f"- [{e.source_id}] {e.type} ({e.status}) affecting {', '.join(e.affects)}{span}.{by}"
            )
        return "\n".join(lines)
