"""add exilus_topics table

The Exilus front-end's per-topic pinned-artifact row: one row per named
subject, holding the pinned TopicBrief (research, ticket 02) and FactionMap
(audience camps, ticket 05) as JSON columns. ``topic`` is unique so a
refresh writes as an UPDATE against the same row (replace semantics) rather
than an INSERT of a duplicate. Both artifact columns land in this one
migration; ticket 05 adds no migration of its own.

Revision ID: dbac9327ac96
Revises: a7c2e91d4b58
Create Date: 2026-07-17 02:34:41.812366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dbac9327ac96'
down_revision: Union[str, Sequence[str], None] = 'a7c2e91d4b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'exilus_topics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=512), nullable=False),
        sa.Column('brief_json', sa.JSON(), nullable=True),
        sa.Column('faction_map_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_exilus_topics_topic'), 'exilus_topics', ['topic'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_exilus_topics_topic'), table_name='exilus_topics')
    op.drop_table('exilus_topics')
