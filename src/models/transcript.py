"""
Transcripts extracted from video captions/subtitles.

PIPELINE ROLE:
  RawContentItem (with subtitle_url) → Transcript fetcher → clean text → Blueprint extraction → RAG indexing

WHY THIS FILE EXISTS:
  Videos often have subtitles. These provide text-based signal for viral mechanics
  (what's being said, when, hook timing). TranscriptFetcher (src/enrichment/transcripts.py)
  downloads and deduplicates TikTok's WebVTT files, then stores clean text here.

DESIGN:
  - 1:1 with RawContentItem (unique constraint on content_item_id)
  - Deduplication at fetch time removes TikTok CDN repeating segments
  - Stored as plain text for easy downstream use (Blueprint extraction, RAG embedding)
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class Transcript(Base):
    """
    Clean transcript text extracted from video subtitles.
    
    Fields:
      content_item_id: reference to RawContentItem (1:1 relationship, unique)
      text: plain-text transcript (deduped, no timestamps)
      source: where the transcript came from (e.g., 'apify_subtitles')
      fetched_at: timestamp when transcript was downloaded and parsed
    """
    __tablename__ = "transcripts"
    __table_args__ = (
        UniqueConstraint("content_item_id", name="uniq_transcript_content_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("raw_content_items.id"), unique=True, index=True
    )

    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())