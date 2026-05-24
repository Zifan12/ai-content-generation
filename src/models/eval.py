"""
Eval infrastructure — golden labels and eval run tracking.

PIPELINE ROLE:
  Ground truth labels (GoldenLabel) → Eval harness → Compare predictions → Record metrics (EvalRun)

WHY THIS FILE EXISTS:
  P1 foundation requires measurable ground truth. GoldenLabel captures human-reviewed
  virality judgments. EvalRun tracks benchmark results (score, metric, git SHA) so we
  can detect regressions and measure improvement over time.

KEY DESIGN:
  - GoldenLabel: 1:1 with RawContentItem, created by scripts/label.py
  - EvalRun: immutable audit trail of metric computation (who ran it, what branch, when)
  - git_sha in EvalRun enables reproducibility: trace any regression to a specific commit
"""

from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class GoldenLabel(Base):
    """
    Human-reviewed ground truth label for a video's virality class.
    
    Created by scripts/label.py: human annotator watches video and assigns class.
    Used by eval harness to measure classifier/extractor accuracy.
    
    Fields:
      content_item_id: reference to RawContentItem (unique, one label per video)
      virality_class: "viral", "mid", "flop", or "suspicious" (from labeler choice)
      best_hook_text: optional hook extracted by human (useful for RAG)
      annotator: who labeled it ("zifan", etc.)
      notes: optional human commentary (rationale, edge cases, concerns)
      labeled_at: timestamp when label was saved
    """
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
    """
    Immutable record of a single eval metric computation.
    
    Captured once per benchmark run (e.g., "blueprint-extractor schema_valid_rate")
    on a specific git commit. Enables regression tracking and performance timeline.
    
    Fields:
      component: what was measured ("rule-based-scorer", "blueprint-extractor-v1", etc.)
      git_sha: short commit hash (enables reproduction: git checkout <sha>)
      metric_name: what metric ("auc", "schema_valid_rate", "precision_at_5", etc.)
      metric_value: the computed value (float, semantics depend on metric_name)
      dataset_version: which golden set version (e.g., "v1", "v2")
      run_at: when the eval ran (immutable timestamp)
    """
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    component: Mapped[str] = mapped_column(String(100))
    git_sha: Mapped[str] = mapped_column(String(40))
    metric_name: Mapped[str] = mapped_column(String(100))
    metric_value: Mapped[float] = mapped_column(Float)
    dataset_version: Mapped[str] = mapped_column(String(50))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())