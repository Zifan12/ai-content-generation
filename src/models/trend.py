"""
Raw scraped content items from video platforms (TikTok, YouTube, Instagram).

PIPELINE ROLE:
  Scrape (apidojo/YouTube API) → RawContentItem (this file) → Trend analysis → Blueprint extraction → Generation

WHY THIS FILE EXISTS:
  Normalized schema for all scraped video metadata. Acts as the **single source of truth**
  for content data. All downstream analysis (virality scoring, Blueprint extraction, RAG
  indexing, ML features) depends on this schema.

KEY DESIGN DECISIONS:
  - Platform-agnostic: supports TikTok, YouTube, Instagram with consistent fields
  - Stores raw_apify_payload for audit trail (what was scraped, what got normalized)
  - niche_id: nullable, assigned post-scrape if needed
  - music_is_original: computed property (heuristic: artist == author username)
  - Unique constraint on (platform, platform_content_id) to prevent duplicates
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class RawContentItem(Base):
    """
    Normalized video metadata from Apify/platform scrapers.
    
    Central schema for all scraped content. Fields populated by platform-specific
    scrapers (TikTokScraper, YouTubeScraper) via _normalize_item() patterns.
    
    Key Fields:
      - platform: "tiktok", "youtube", or "instagram" (index for queries)
      - platform_content_id: platform's unique ID (unique with platform)
      - views, likes, comments, shares: engagement metrics (used for virality scoring)
      - audio_id: platform-specific sound/music ID
      - hashtags: list[str], extracted and normalized
      - subtitle_url: direct download URL to WebVTT file (expires ~30 days)
      - niche_id: optional, assigned post-scrape for content classification
      - raw_apify_payload: full JSON response from Apify actor (audit trail)
      - published_at, collected_at: timestamps for temporal analysis
    
    Constraints:
      - (platform, platform_content_id) must be unique (prevents duplicates)
      - title, description, author_username indexed for search
    """ 
    __tablename__ = "raw_content_items"
    __table_args__ = (
        UniqueConstraint("platform", "platform_content_id", name="uniq_raw_platform_content_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    niche_id: Mapped[int | None] = mapped_column(ForeignKey("niches.id"), index=True)

    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_content_id: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(Text)

    views: Mapped[int] = mapped_column(default=0)
    likes: Mapped[int] = mapped_column(default=0)
    comments: Mapped[int] = mapped_column(default=0)
    shares: Mapped[int] = mapped_column(default=0)
    collect_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    audio_id: Mapped[str | None] = mapped_column(String(255))
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    duration_in_seconds: Mapped[int | None] = mapped_column()
    content_format: Mapped[str | None] = mapped_column(String(50), index=True)

    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    music_audio_url: Mapped[str | None] = mapped_column(Text)
    video_download_url: Mapped[str | None] = mapped_column(Text)
    video_aspect_ratio: Mapped[str | None] = mapped_column(String(16))
    subtitle_url: Mapped[str | None] = mapped_column(Text)

    author_username: Mapped[str | None] = mapped_column(String(100), index=True)
    author_tiktok_id: Mapped[str | None] = mapped_column(String(32), index=True)

    poi_name: Mapped[str | None] = mapped_column(String(255))
    poi_country: Mapped[str | None] = mapped_column(String(8))
    input_source: Mapped[str | None] = mapped_column(Text)
    raw_apify_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    @property
    def music_is_original(self) -> bool | None:
        """True if track artist matches author username (case-insensitive).

        Heuristic for `musicMeta.musicOriginal` which apidojo does not return directly.
        Returns None when raw_apify_payload is missing or the song.artist field is absent.
        """
        if not self.raw_apify_payload:
            return None
        
        song = self.raw_apify_payload.get("song") or {}
        artist = song.get("artist")

        if not artist or not self.author_username:
            return None
        
        return artist.strip().lower() == self.author_username.strip().lower()



class DetectedTrend(Base):
    __tablename__ = "detected_trends"

    id: Mapped[int] = mapped_column(primary_key=True)
    niche_id: Mapped[int | None] = mapped_column(ForeignKey("niches.id"), index=True)

    trend_type: Mapped[str] = mapped_column(String(30), index=True)
    label: Mapped[str] = mapped_column(String(255), index=True)

    confidence_score: Mapped[float] = mapped_column()
    velocity_score: Mapped[float] = mapped_column()
    supporting_content_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)