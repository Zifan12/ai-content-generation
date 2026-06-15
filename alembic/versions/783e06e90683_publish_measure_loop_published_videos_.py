"""publish_measure_loop: published_videos + blueprint outcome_view_percentile

Revision ID: 783e06e90683
Revises: 7a492259a3c1
Create Date: 2026-06-15 15:24:29.077356

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '783e06e90683'
down_revision: Union[str, Sequence[str], None] = '7a492259a3c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Hand-trimmed: autogenerate also emitted unrelated drift (drop miner_rankings, drop
    eval_runs/golden_labels/viral_videos indexes, add author_tiktok_id index) from
    pre-existing model/DB skew. That drift is NOT part of this change and was removed —
    only the two real changes (published_videos table + blueprints.outcome_view_percentile)
    are applied here.
    """
    op.create_table('published_videos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('blueprint_id', sa.Integer(), nullable=False),
    sa.Column('niche', sa.String(length=100), nullable=False),
    sa.Column('tiktok_url', sa.String(length=500), nullable=False),
    sa.Column('post_id', sa.String(length=100), nullable=True),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('view_7d', sa.Integer(), nullable=True),
    sa.Column('like_7d', sa.Integer(), nullable=True),
    sa.Column('comment_7d', sa.Integer(), nullable=True),
    sa.Column('share_7d', sa.Integer(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['blueprint_id'], ['blueprints.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_published_videos_blueprint_id'), 'published_videos', ['blueprint_id'], unique=False)
    op.add_column('blueprints', sa.Column('outcome_view_percentile', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('blueprints', 'outcome_view_percentile')
    op.drop_index(op.f('ix_published_videos_blueprint_id'), table_name='published_videos')
    op.drop_table('published_videos')
