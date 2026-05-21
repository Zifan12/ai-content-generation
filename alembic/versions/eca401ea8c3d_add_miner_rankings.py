"""add miner_rankings

Revision ID: eca401ea8c3d
Revises: f7322c3f9332
Create Date: 2026-05-20 20:40:45.396950

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eca401ea8c3d'
down_revision: Union[str, Sequence[str], None] = 'f7322c3f9332'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "miner_rankings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("niche_label", sa.String(100), nullable=False, index=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("blueprint_template", sa.JSON(), nullable=False),
        sa.Column("matching_items", sa.Integer(), nullable=False),
        sa.Column("median_views", sa.Integer(), nullable=False),
        sa.Column("p90_views", sa.Integer(), nullable=False),
        sa.Column("trend_slope_4wk_pct", sa.Float(), nullable=False),
        sa.Column("rationale", sa.String(280), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_miner_rankings_run_niche", "miner_rankings", ["run_id", "niche_label"])


def downgrade() -> None:
    op.drop_index("ix_miner_rankings_run_niche", table_name="miner_rankings")
    op.drop_table("miner_rankings")
