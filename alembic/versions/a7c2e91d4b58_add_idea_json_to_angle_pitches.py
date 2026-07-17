"""add idea_json to angle_pitches (staged-director slice ①)

The pitcher now persists its desire-only IdeaPitch per slate entry in
idea_json; story_json holds the StoryArchitect's developed StoryScript and is
NULL for ideas that were never picked. Pre-slice rows keep idea_json NULL.

Revision ID: a7c2e91d4b58
Revises: 591b760656eb
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c2e91d4b58'
down_revision: Union[str, Sequence[str], None] = '591b760656eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('angle_pitches', sa.Column('idea_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('angle_pitches', 'idea_json')
