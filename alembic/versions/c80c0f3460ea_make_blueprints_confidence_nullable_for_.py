"""make blueprints.confidence nullable for v3

Revision ID: c80c0f3460ea
Revises: cdc82fdf26bd
Create Date: 2026-05-11 19:16:59.972559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c80c0f3460ea'
down_revision: Union[str, Sequence[str], None] = 'cdc82fdf26bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v3 Blueprint drops LLM-emitted confidence (ADR-0001). Column stays for
    # audit of v1 rows; new v3 rows write NULL.
    with op.batch_alter_table("blueprints") as batch_op:
        batch_op.alter_column("confidence", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("blueprints") as batch_op:
        batch_op.alter_column("confidence", existing_type=sa.Float(), nullable=False)
