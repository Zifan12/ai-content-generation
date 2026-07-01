"""add context_bundle to trending_events

Revision ID: 25eee929d4e5
Revises: c9d1e2f3a4b5
Create Date: 2026-06-30 18:06:57.418308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25eee929d4e5'
down_revision: Union[str, Sequence[str], None] = 'c9d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "trending_events",
        sa.Column("context_bundle", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("trending_events", "context_bundle")
