"""add usage_cache_write_tokens to extractor_responses

Revision ID: f7322c3f9332
Revises: 371ad2811047
Create Date: 2026-05-14 17:00:21.429356

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7322c3f9332'
down_revision: Union[str, Sequence[str], None] = '371ad2811047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add usage_cache_write_tokens column for tracking prompt-cache write costs."""
    op.add_column(
        'extractor_responses',
        sa.Column('usage_cache_write_tokens', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop usage_cache_write_tokens column."""
    op.drop_column('extractor_responses', 'usage_cache_write_tokens')
