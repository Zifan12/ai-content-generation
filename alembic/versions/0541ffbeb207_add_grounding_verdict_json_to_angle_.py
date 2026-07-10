"""add grounding_verdict_json to angle_pitches

Revision ID: 0541ffbeb207
Revises: f03d6a6940a9
Create Date: 2026-07-10 16:58:52.613033

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0541ffbeb207'
down_revision: Union[str, Sequence[str], None] = 'f03d6a6940a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Hand-trimmed: autogenerate polluted this with spurious drops of tables/
    # indexes it can't see in target_metadata (web_research_chunks, miner_rankings,
    # HNSW indexes). Only the grounding_verdict_json add is this migration's change.
    op.add_column('angle_pitches', sa.Column('grounding_verdict_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('angle_pitches', 'grounding_verdict_json')
