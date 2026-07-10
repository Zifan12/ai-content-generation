from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from src.database import Base


class WebResearchChunk(Base):
    """One embedded chunk of raw web-research text — a row in the "fridge".

    Persists a slice of the ContextAgent's web research (tavily_search +
    firecrawl_extract) that ``_finalize`` would otherwise compress into the
    bundle summary and discard, so a downstream stage can retrieve the specific
    detail on demand instead of re-paying for a search. Scoped by ``topic`` (the
    ``--topic`` that gathered it); within-run retrieval filters on ``topic`` then
    orders by cosine distance on ``embedding`` (HNSW index). Mirrors the pgvector
    + provenance shape of :class:`ViralVideo`.

    ``source_url`` is nullable: a chunk built from aggregated tavily snippets may
    not trace to a single page. ``embedding_model`` records which embedder
    produced the vector, so a future embedder swap can detect stale rows.
    """

    __tablename__ = "web_research_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
