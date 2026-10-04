"""Reports and ratings tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None

TABLES = ("road_reports", "site_status_reports", "advice_ratings")


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("site_id", sa.String(64), nullable=False, index=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "road_reports",
        *_common(),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=False),
        sa.Column("condition", sa.String(16), nullable=False),
        sa.Column("lat", sa.Float),
        sa.Column("lon", sa.Float),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
    )
    op.create_table(
        "site_status_reports",
        *_common(),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("lat", sa.Float),
        sa.Column("lon", sa.Float),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
    )
    op.create_table(
        "advice_ratings",
        *_common(),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("helpful", sa.Boolean, nullable=False),
        sa.Column("comment", sa.String(500), nullable=False, server_default=""),
    )
    if op.get_bind().dialect.name == "postgresql":
        # Supabase exposes every public table through its REST API. This app reaches the tables
        # only through its own server connection, so turn on row-level security with no policies:
        # the REST API (anon key) then sees nothing, while the server role is unaffected.
        for table in TABLES:
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
