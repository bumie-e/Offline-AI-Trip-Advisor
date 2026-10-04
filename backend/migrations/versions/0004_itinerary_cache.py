"""Cache of model-written itineraries, which also counts model calls per day.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.create_table(
        "itinerary_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("site_id", sa.String(64), nullable=False, index=True),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.itinerary_cache ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("itinerary_cache")
