from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class GoldenLabel(Base):
    __tablename__ = "golden_labels"
    __table_args__ = (
        UniqueConstraint("content_item_id", name="uniq_golden_label_content_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("raw_content_items.id"), index=True)
    virality_class: Mapped[str] = mapped_column(String(20))
    best_hook_text: Mapped[str | None] = mapped_column(Text)
    annotator: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    labeled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    component: Mapped[str] = mapped_column(String(100))
    git_sha: Mapped[str] = mapped_column(String(40))
    metric_name: Mapped[str] = mapped_column(String(100))
    metric_value: Mapped[float] = mapped_column(Float)
    dataset_version: Mapped[str] = mapped_column(String(50))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())