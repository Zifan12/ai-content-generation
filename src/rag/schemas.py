"""Pydantic schemas for RAG retrieval requests/responses.

Hits embed blueprint_data + niche_label to avoid per-result DB joins downstream.
"""

from pydantic import BaseModel, Field

from src.miner.schemas import BlueprintCandidate


class RetrievalQuery(BaseModel):
    """Request envelope passed to BlueprintRetriever.retrieve.

    Single typed object beats two raw args — extensible (future niche / score-floor
    filters land as new fields without churning the retrieve() signature).
    """
    candidate: BlueprintCandidate
    top_k: int = Field(default=5, ge=1, le=100)


class RetrievalHit(BaseModel):
    """One row of retriever output, hydrated from the (viral_videos × blueprints) join.

    score is cosine similarity in [-1, 1] — BGE-M3 produces normalized vectors,
    so in practice scores land in [0, 1]. niche_label is denormalized from
    blueprint_data["niche_label"] for caller convenience; missing key falls
    back to "unknown".
    """
    content_item_id: int
    blueprint_id: int
    score: float
    blueprint_data: dict
    niche_label: str


class RetrievalResponse(BaseModel):
    """Envelope returned by BlueprintRetriever.retrieve.

    query echoed back for trace/replay/audit. hits sorted by score descending.
    elapsed_ms is wall-clock of retrieve() only; embedder model load is caller's
    responsibility and not included.
    """
    query: RetrievalQuery
    hits: list[RetrievalHit]
    elapsed_ms: float