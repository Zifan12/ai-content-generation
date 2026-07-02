from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AnglePitchRecord(Base):
    __tablename__ = "angle_pitches"
    id: Mapped[int] = mapped_column(primary_key=True)
    trending_event_id: Mapped[int] = mapped_column(ForeignKey("trending_events.id"))
    take: Mapped[str] = mapped_column(Text, nullable=False)
    # Legacy routing-era columns — nullable now that the story-craft path
    # (story_json/mode/craft_verdict_json) supersedes them (Stage B).
    format_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_backend: Mapped[str | None] = mapped_column(String, nullable=True)
    # Story-craft columns (Stage B): the full StoryPitch, its bound mode, the
    # gate's verdict, and whether the craft gate killed it (killed pitches are
    # persisted as future negative examples).
    story_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mode: Mapped[str | None] = mapped_column(String, nullable=True)
    craft_verdict_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    killed_by_gate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    estimated_cost_credits: Mapped[float] = mapped_column(Float, nullable=False)
    gap_satisfaction_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    legal_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
