from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class RawContentItem(Base): 
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

    audio_id: Mapped[str | None] = mapped_column(String(255))
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    duration_in_seconds: Mapped[int | None] = mapped_column()
    content_format: Mapped[str | None] = mapped_column(String(50), index=True)

    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(Text)
    subtitle_url: Mapped[str | None] = mapped_column(Text)
    author_username: Mapped[str | None] = mapped_column(String(100), index=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

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