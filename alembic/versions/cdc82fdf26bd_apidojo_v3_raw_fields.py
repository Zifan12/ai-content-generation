"""apidojo v3 raw fields

Revision ID: cdc82fdf26bd
Revises: 1b0f95a14e99
Create Date: 2026-05-11 12:51:07.263708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdc82fdf26bd'
down_revision: Union[str, Sequence[str], None] = '1b0f95a14e99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "raw_content_items",
        "video_url",
        new_column_name="music_audio_url",
    )
    op.add_column("raw_content_items", sa.Column("collect_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("raw_content_items", sa.Column("video_download_url", sa.Text(), nullable=True))
    op.add_column("raw_content_items", sa.Column("video_aspect_ratio", sa.String(16), nullable=True))
    op.add_column("raw_content_items", sa.Column("author_tiktok_id", sa.String(32), nullable=True))
    op.add_column("raw_content_items", sa.Column("poi_name", sa.String(255), nullable=True))
    op.add_column("raw_content_items", sa.Column("poi_country", sa.String(8), nullable=True))
    op.add_column("raw_content_items", sa.Column("input_source", sa.Text(), nullable=True))
    op.add_column("raw_content_items", sa.Column("raw_apify_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_content_items", "raw_apify_payload")
    op.drop_column("raw_content_items", "input_source")
    op.drop_column("raw_content_items", "poi_country")
    op.drop_column("raw_content_items", "poi_name")
    op.drop_column("raw_content_items", "author_tiktok_id")
    op.drop_column("raw_content_items", "video_aspect_ratio")
    op.drop_column("raw_content_items", "video_download_url")
    op.drop_column("raw_content_items", "collect_count")
    op.alter_column(
        "raw_content_items",
        "music_audio_url",
        new_column_name="video_url",
    )
