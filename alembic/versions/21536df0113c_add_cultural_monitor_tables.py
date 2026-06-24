"""add cultural monitor tables

Revision ID: 21536df0113c
Revises: 783e06e90683
Create Date: 2026-06-24 15:41:53.366819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '21536df0113c'
down_revision: Union[str, Sequence[str], None] = '783e06e90683'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Hand-trimmed: autogenerate also emitted the same unrelated pre-existing drift the
    783e06e90683 migration documented (drop miner_rankings + its indexes, drop
    eval_runs/golden_labels indexes, add ix_raw_content_items_author_tiktok_id, drop the
    viral_videos HNSW index). That drift is NOT part of this change and was removed — only
    the three real changes are applied: create trending_events, create angle_pitches, and
    extend published_videos (5 news-reactive columns + angle_pitch_id FK + blueprint_id
    made nullable so a posted video can be sourced by EITHER a blueprint or an angle pitch).
    """
    op.create_table('trending_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('headline', sa.String(), nullable=False),
    sa.Column('reaction_sample', sa.Text(), nullable=False),
    sa.Column('trendiness_score', sa.Float(), nullable=False),
    sa.Column('virality_window_hours', sa.Float(), nullable=False),
    sa.Column('dominant_emotion', sa.String(), nullable=True),
    sa.Column('audience_want', sa.String(), nullable=True),
    sa.Column('gap_type', sa.String(), nullable=True),
    sa.Column('producibility_score', sa.Float(), nullable=True),
    sa.Column('composite_score', sa.Float(), nullable=True),
    sa.Column('selected_for_pitching', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('angle_pitches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trending_event_id', sa.Integer(), nullable=False),
    sa.Column('take', sa.Text(), nullable=False),
    sa.Column('format_description', sa.Text(), nullable=False),
    sa.Column('render_backend', sa.String(), nullable=False),
    sa.Column('estimated_cost_credits', sa.Float(), nullable=False),
    sa.Column('gap_satisfaction_rationale', sa.Text(), nullable=False),
    sa.Column('legal_flag', sa.Boolean(), nullable=False),
    sa.Column('approved', sa.Boolean(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['trending_event_id'], ['trending_events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('published_videos', sa.Column('angle_pitch_id', sa.Integer(), nullable=True))
    op.add_column('published_videos', sa.Column('trendiness_score_at_post', sa.Float(), nullable=True))
    op.add_column('published_videos', sa.Column('gap_type', sa.String(), nullable=True))
    op.add_column('published_videos', sa.Column('format_backend', sa.String(), nullable=True))
    op.add_column('published_videos', sa.Column('virality_window_hours_remaining', sa.Float(), nullable=True))
    op.alter_column('published_videos', 'blueprint_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.create_foreign_key(
        'fk_published_videos_angle_pitch_id',
        'published_videos', 'angle_pitches', ['angle_pitch_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema (mirror of the hand-trimmed upgrade)."""
    op.drop_constraint('fk_published_videos_angle_pitch_id', 'published_videos', type_='foreignkey')
    op.alter_column('published_videos', 'blueprint_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('published_videos', 'virality_window_hours_remaining')
    op.drop_column('published_videos', 'format_backend')
    op.drop_column('published_videos', 'gap_type')
    op.drop_column('published_videos', 'trendiness_score_at_post')
    op.drop_column('published_videos', 'angle_pitch_id')
    op.drop_table('angle_pitches')
    op.drop_table('trending_events')
