"""story pitch columns

Revision ID: ccea17dacec5
Revises: 25eee929d4e5
Create Date: 2026-07-02 17:09:03.906957

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ccea17dacec5'
down_revision: Union[str, Sequence[str], None] = '25eee929d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Story-craft columns on angle_pitches (Stage B); the legacy routing columns
    become nullable now that the story path supersedes them. Autogenerate drift
    on unrelated tables (miner_rankings, eval_runs/golden_labels/raw_content_items/
    viral_videos indexes) was trimmed out — this revision touches angle_pitches only.
    """
    op.add_column('angle_pitches', sa.Column('story_json', sa.JSON(), nullable=True))
    op.add_column('angle_pitches', sa.Column('mode', sa.String(), nullable=True))
    op.add_column('angle_pitches', sa.Column('craft_verdict_json', sa.JSON(), nullable=True))
    op.add_column('angle_pitches', sa.Column('killed_by_gate', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.alter_column('angle_pitches', 'format_description',
               existing_type=sa.TEXT(),
               nullable=True)
    op.alter_column('angle_pitches', 'render_backend',
               existing_type=sa.VARCHAR(),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('angle_pitches', 'render_backend',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('angle_pitches', 'format_description',
               existing_type=sa.TEXT(),
               nullable=False)
    op.drop_column('angle_pitches', 'killed_by_gate')
    op.drop_column('angle_pitches', 'craft_verdict_json')
    op.drop_column('angle_pitches', 'mode')
    op.drop_column('angle_pitches', 'story_json')
