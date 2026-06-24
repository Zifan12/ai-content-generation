"""
Published-video tracking — one row per AI-generated video posted to TikTok (P3.5).

PIPELINE ROLE:
  BlueprintRecord (target) → content_writer → manual render (Higgsfield) → manual TikTok post
  → PublishedVideo (this file) → day-7 view count → self-relative percentile written back
  to BlueprintRecord.outcome_view_percentile → P4 label.

WHY THIS FILE EXISTS:
  P3.5 closes the feedback loop. Posting + rendering are MANUAL; the code only does DB-side
  measurement. Each posted video gets one row here recording which blueprint conditioned it,
  the live TikTok URL, when it was posted, and (filled later) its 7-day view/like/share counts.

KEY FIELDS:
  - blueprint_id: FK to the BlueprintRecord that conditioned this video. THE closed-loop link —
    lets the day-7 outcome be written back onto the blueprint as the P4 ground-truth label.
  - niche: denormalized (e.g. 'surreal_hyperreal') for easy per-niche percentile grouping.
  - tiktok_url: the live post URL, pasted in by hand after manual upload.
  - post_id: platform video id (optional; may be parsed from the URL later, not required now).
  - posted_at: drives the "is it 7 days old yet?" clock.
  - view_7d / like_7d / comment_7d / share_7d: the day-7 snapshot. NULLABLE = not measured yet
    (the count is read once, manually, ~7 days after posting; views climb forever so the label
    is pinned to that fixed snapshot). view_7d is the label source; the others are secondary
    engagement signals kept in case P4 wants them as features.
  - fetched_at: when the day-7 count was read (audit + future staleness logic).
"""

from datetime import date, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class PublishedVideo(Base):
    """
    One row per AI-generated video manually posted to TikTok.

    Links back to the conditioning BlueprintRecord via blueprint_id (the closed-loop link).
    View/like/share counts are nullable because they are filled in a separate manual pass at
    the 7-day mark, not at insert time. compute_percentiles later ranks all rows with a
    non-null view_7d and writes each one's self-relative percentile to the linked blueprint.
    """
    
    __tablename__ = "published_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    blueprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("blueprints.id"), index=True, nullable=True
    )  # closed-loop link to the conditioning blueprint (old path; null for news-reactive videos)
    niche: Mapped[str] = mapped_column(String(100))
    tiktok_url: Mapped[str] = mapped_column(String(500))
    post_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    view_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    angle_pitch_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("angle_pitches.id"), nullable=True
    )  # news-reactive path; null for old blueprint-sourced videos
    trendiness_score_at_post: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap_type: Mapped[str | None] = mapped_column(String, nullable=True)
    format_backend: Mapped[str | None] = mapped_column(String, nullable=True)
    virality_window_hours_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)