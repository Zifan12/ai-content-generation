from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class TrendingEventRecord(Base):
    __tablename__ = "trending_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="reddit")
    headline: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    reaction_sample: Mapped[str] = mapped_column(Text, nullable=False)
    trendiness_score: Mapped[float] = mapped_column(Float, nullable=False)
    virality_window_hours: Mapped[float] = mapped_column(Float, nullable=False)
    dominant_emotion: Mapped[str | None] = mapped_column(String, nullable=True)
    audience_want: Mapped[str | None] = mapped_column(String, nullable=True)
    gap_type: Mapped[str | None] = mapped_column(String, nullable=True)
    producibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected_for_pitching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
