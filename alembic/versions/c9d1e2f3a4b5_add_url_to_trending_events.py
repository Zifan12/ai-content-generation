"""add url to trending_events

Revision ID: c9d1e2f3a4b5
Revises: 21536df0113c
Create Date: 2026-06-26 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = '21536df0113c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable ``url`` column to ``trending_events``.

    Lets a persisted event be traced back to its exact Reddit post. Nullable so
    existing rows (and any source that lacks a URL) remain valid without a backfill.
    """
    op.add_column('trending_events', sa.Column('url', sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the ``url`` column from ``trending_events``."""
    op.drop_column('trending_events', 'url')
