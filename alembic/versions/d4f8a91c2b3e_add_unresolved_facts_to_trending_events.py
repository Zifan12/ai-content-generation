"""add unresolved_facts to trending_events

Revision ID: d4f8a91c2b3e
Revises: ccea17dacec5
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4f8a91c2b3e'
down_revision: Union[str, Sequence[str], None] = 'ccea17dacec5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable ``unresolved_facts`` JSON column to ``trending_events``.

    Holds the list of specific facts the context agent tried to verify and
    couldn't confirm (Path B only). Nullable so every pre-existing row, and
    every Path A row (which never builds a bundle), stays valid with no
    backfill.
    """
    op.add_column(
        'trending_events', sa.Column('unresolved_facts', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Drop the ``unresolved_facts`` column from ``trending_events``."""
    op.drop_column('trending_events', 'unresolved_facts')
