"""add golden_labels and eval_runs

Revision ID: 2b8da12d6923
Revises: 1d2adbac0466
Create Date: 2026-04-26 16:29:57.550501

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b8da12d6923'
down_revision: Union[str, Sequence[str], None] = '1d2adbac0466'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'golden_labels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content_item_id', sa.Integer(), nullable=False),
        sa.Column('virality_class', sa.String(length=20), nullable=False),
        sa.Column('best_hook_text', sa.Text(), nullable=True),
        sa.Column('annotator', sa.String(length=100), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('labeled_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['content_item_id'], ['raw_content_items.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('content_item_id', name='uniq_golden_label_content_item'),
    )
    op.create_index(op.f('ix_golden_labels_content_item_id'), 'golden_labels', ['content_item_id'], unique=False)
    op.create_index(op.f('ix_golden_labels_virality_class'), 'golden_labels', ['virality_class'], unique=False)

    op.create_table(
        'eval_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('component', sa.String(length=100), nullable=False),
        sa.Column('git_sha', sa.String(length=40), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('dataset_version', sa.String(length=50), nullable=False),
        sa.Column('run_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_eval_runs_component'), 'eval_runs', ['component'], unique=False)
    op.create_index(op.f('ix_eval_runs_metric_name'), 'eval_runs', ['metric_name'], unique=False)
    op.create_index(op.f('ix_eval_runs_run_at'), 'eval_runs', ['run_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_eval_runs_run_at'), table_name='eval_runs')
    op.drop_index(op.f('ix_eval_runs_metric_name'), table_name='eval_runs')
    op.drop_index(op.f('ix_eval_runs_component'), table_name='eval_runs')
    op.drop_table('eval_runs')
    op.drop_index(op.f('ix_golden_labels_virality_class'), table_name='golden_labels')
    op.drop_index(op.f('ix_golden_labels_content_item_id'), table_name='golden_labels')
    op.drop_table('golden_labels')
