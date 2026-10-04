import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from trip_advisor.api.routes import delta, images, itinerary, pack, places, reports

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Offline-First Itinerary Advisor")

    @app.exception_handler(SQLAlchemyError)
    def database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Missing tables, a bad URL or an outage: log the cause, tell the client only that it
        # can retry. Queued reports stay on the device until a sync succeeds.
        log.error("database error: %s", exc)
        return JSONResponse({"detail": "Reports are temporarily unavailable"}, status_code=503)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (places, itinerary, pack, delta, reports, images):
        app.include_router(module.router)
    return app


app = create_app()
