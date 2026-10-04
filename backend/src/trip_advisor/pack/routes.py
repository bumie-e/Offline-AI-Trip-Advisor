"""Convert collected routes into the shape the app downloads."""

from trip_advisor.pipeline.collect.models import SiteRoutes
from trip_advisor.pipeline.generate.evidence import route_id
from trip_advisor.schemas.routes import PackPlace, PackRoute, PackRoutes, PackStop


def to_pack_routes(routes: SiteRoutes) -> PackRoutes:
    return PackRoutes(
        origin=PackPlace(name=routes.origin.name, lat=routes.origin.lat, lon=routes.origin.lon),
        destination=PackPlace(
            name=routes.destination.name, lat=routes.destination.lat, lon=routes.destination.lon
        ),
        routes=[
            PackRoute(
                cite_id=route_id(routes.site_id, r),
                id=r.id,
                kind=r.kind,
                label=r.label,
                distance_km=r.distance_km,
                duration_min=r.duration_min,
                roads=r.roads,
            )
            for r in routes.routes
        ],
        stops=[
            PackStop(
                name=s.name,
                kind=s.kind,
                lat=s.lat,
                lon=s.lon,
                km_from_start=s.km_from_start,
                route_id=s.route_id,
            )
            for s in routes.stops
        ],
        collected_at=routes.collected_at,
    )
