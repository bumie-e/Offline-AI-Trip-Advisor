"""Vercel entrypoint: Vercel looks for an `app` object in index.py at the project root."""

from trip_advisor.main import app

__all__ = ["app"]
