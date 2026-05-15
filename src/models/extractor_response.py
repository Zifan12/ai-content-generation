"""
Raw LLM response cache for Blueprint extraction.

Stores the model's raw output keyed by (content_item_id, prompt_fingerprint)
so schema bumps can re-validate cached data without re-calling the API.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class ExtractorResponse(Base):
    """
    Stores raw LLM extraction responses keyed by content item and prompt fingerprint.

    This table supports deterministic re-parse workflows and token/cost tracking
    without re-calling the model when prompt inputs are unchanged.
    """

    __tablename__ = "extractor_responses"
    __table_args__ = (
        UniqueConstraint("content_item_id", "prompt_fingerprint", name="uniq_extractor_response_item_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("raw_content_items.id"), nullable=False, index=True)

    prompt_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    envelope: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    usage_output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    usage_cache_read_tokens: Mapped[int | None] = mapped_column(nullable=True)
    usage_cache_write_tokens: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
