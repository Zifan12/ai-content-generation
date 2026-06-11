"""
Blueprint extraction and versioning — LLM-extracted virality mechanics from videos.

PIPELINE ROLE:
  RawContentItem → Transcript → LLM extraction → BlueprintRecord (this file) → RAG retrieval → Generation

WHY THIS FILE EXISTS:
  P1.5 Foundation (2026-05-10): Every scraped video needs a structured Blueprint
  extracted via Claude Sonnet + instructor. This replaces manual pattern annotation.
  
  Blueprints encode viral mechanics: hook type, pacing, visual complexity, aesthetic,
  narrative structure. They ground RAG retrieval and feed ML features for the P4 predictor.

VERSIONING STRATEGY:
  Schema evolves over time (v0: narrative strings → v1: enums → v2: niche-specific →
  v3: niche-agnostic). The unique constraint on (content_item_id, extractor_version)
  means we keep all historical versions. This allows:
  - Schema changes without data loss
  - A/B testing different extractors
  - Rollback to earlier versions if a new extractor regresses

KEY FIELDS:
  - extractor_version: schema stamp (e.g., 'v3'). Changes here = schema breaking change.
  - extractor_model: which LLM model created this (e.g., 'claude-sonnet-4-6').
  - blueprint_data: JSON-serialized Pydantic object with the extracted mechanics.
  - confidence: optional float (0.0-1.0) for extractor confidence in this Blueprint.

EVAL GATE:
  CI gate: schema_valid_rate ≥ 0.95. If >5% of Blueprints fail validation,
  extraction is broken and the pipeline stalls.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class BlueprintRecord(Base):
    """
    Versioned Blueprint storage — one JSON record per (content_item, extractor_version) pair.
    
    Stores LLM-extracted virality mechanics (hook type, pacing, visual complexity, etc.)
    as a JSON-serialized Pydantic schema.
    
    Unique constraint on (content_item_id, extractor_version) allows schema evolution:
    - Add new fields by bumping extractor_version
    - Keep historical data for audit and retraining
    - Query by version for eval gates (e.g., find all v3 Blueprints with schema_valid_rate)
    """

    __tablename__ = "blueprints"
    __table_args__ = (
        UniqueConstraint(
            "content_item_id",
            "extractor_version", # Versioning stamp on Blueprint schema. Lets schema evolve without losing old data
            name="uniq_blueprint_content_extractor_version",
        ),
    ) 

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("raw_content_items.id"), index=True)
    extractor_version: Mapped[str] = mapped_column(String(20), index=True)
    extractor_model: Mapped[str] = mapped_column(String(100))
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    blueprint_data: Mapped[dict[str, Any]] = mapped_column(JSON) # Stored Blueprint Pydantic objects as JSON dict in SQLite/Postgres: src/blueprints/schema.py 

