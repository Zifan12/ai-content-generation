"""add pgvector and viral_videos

Revision ID: 7a492259a3c1
Revises: eca401ea8c3d
Create Date: 2026-05-22 17:03:46.688690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '7a492259a3c1'
down_revision: Union[str, Sequence[str], None] = 'eca401ea8c3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # pgvector extension — Postgres only (SQLite skips).
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "viral_videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Integer(),
            sa.ForeignKey("raw_content_items.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "blueprint_id",
            sa.Integer(),
            sa.ForeignKey("blueprints.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("embedding_model", sa.String(64), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embed_text_hash", sa.String(64), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Vector column + HNSW index — Postgres only.
    if bind.dialect.name == "postgresql":
        op.add_column(
            "viral_videos",
            sa.Column("embedding", Vector(1024), nullable=False),
        )
        op.execute(
            "CREATE INDEX viral_videos_embedding_hnsw ON viral_videos "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS viral_videos_embedding_hnsw")
    op.drop_table("viral_videos")
    # pgvector extension left installed; harmless and reusable by other tables.
