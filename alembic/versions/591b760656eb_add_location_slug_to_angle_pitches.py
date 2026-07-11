"""add location_slug to angle_pitches

Revision ID: 591b760656eb
Revises: 0541ffbeb207
Create Date: 2026-07-11 13:48:27.306571

Hand-trimmed: autogenerate compared the models against a drifted local DB and
proposed dropping unrelated tables/indexes (miner_rankings, web_research_chunks,
the viral_videos HNSW index, several eval_runs indexes). All of that is
pre-existing model/DB drift, NOT this change — stripped so this migration adds
ONLY the location_slug column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '591b760656eb'
down_revision: Union[str, Sequence[str], None] = '0541ffbeb207'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable location_slug column to angle_pitches."""
    op.add_column('angle_pitches', sa.Column('location_slug', sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the location_slug column."""
    op.drop_column('angle_pitches', 'location_slug')
