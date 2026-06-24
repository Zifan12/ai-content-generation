from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AnglePitchRecord(Base):
    __tablename__ = "angle_pitches"
    id: Mapped[int] = mapped_column(primary_key=True)
    trending_event_id: Mapped[int] = mapped_column(ForeignKey("trending_events.id"))
    take: Mapped[str] = mapped_column(Text, nullable=False)
    format_description: Mapped[str] = mapped_column(Text, nullable=False)
    render_backend: Mapped[str] = mapped_column(String, nullable=False)
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