"""add web_research_chunks fridge table

Revision ID: f03d6a6940a9
Revises: d4f8a91c2b3e
Create Date: 2026-07-09 23:31:43.270287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'f03d6a6940a9'
down_revision: Union[str, Sequence[str], None] = 'd4f8a91c2b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Creates web_research_chunks (the fridge): one embedded chunk of raw
    web-research text per row, scoped by the topic that gathered it. Postgres
    only (ADR-0006); the HNSW index mirrors viral_videos' pgvector setup.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "web_research_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(512), nullable=False, index=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("embedding_model", sa.String(64), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1024), nullable=False),
    )

    op.execute(
        "CREATE INDEX web_research_chunks_embedding_hnsw ON web_research_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS web_research_chunks_embedding_hnsw")
    op.drop_table("web_research_chunks")
    # pgvector extension left installed; shared with viral_videos.
