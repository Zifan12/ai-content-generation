"""ORM model and persistence helpers for miner ranking runs.

Stores ranked BlueprintCandidate outputs from rank.py into miner_rankings,
one row per candidate per run. A run_id (UUID) groups all candidates from
a single rank invocation so latest_run can reconstruct the full ranked list.
"""
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import DateTime, Float, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, Session

from src.database import Base
from src.miner.schemas import BlueprintCandidate, MinerEvidence


class MinerRanking(Base):
    """One row per BlueprintCandidate per rank run. Grouped by run_id."""

    __tablename__ = "miner_rankings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    niche_label: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    blueprint_template: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    matching_items: Mapped[int] = mapped_column(Integer, nullable=False)
    median_views: Mapped[int] = mapped_column(Integer, nullable=False)
    p90_views: Mapped[int] = mapped_column(Integer, nullable=False)
    trend_slope_4wk_pct: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(String(280), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def persist_run(db: Session, candidates: list[BlueprintCandidate], niche_label: str) -> str:

    run_id = str(uuid.uuid4())

    for candidate in candidates:
        row = MinerRanking(
            run_id=run_id,
            niche_label=niche_label,
            rank=candidate.rank,
            blueprint_template=candidate.blueprint_template,
            matching_items=candidate.evidence.matching_items,
            median_views=candidate.evidence.median_views,
            p90_views=candidate.evidence.p90_views,
            trend_slope_4wk_pct=candidate.evidence.trend_slope_4wk_pct,
            rationale=candidate.evidence.rationale,
        )

        db.add(row)

    db.commit()

    return run_id

def latest_run(db: Session, niche_label: str) -> list[BlueprintCandidate]:

    latest = db.query(MinerRanking).filter(MinerRanking.niche_label == niche_label).order_by(MinerRanking.created_at.desc()).first()

    if latest is None:
        return []
    
    run_id = latest.run_id
    rows = db.query(MinerRanking).filter(MinerRanking.run_id == run_id).order_by(MinerRanking.rank).all()
    
    return [
        BlueprintCandidate(
            rank=row.rank,
            niche_label=row.niche_label,
            blueprint_template=row.blueprint_template,
            evidence=MinerEvidence(
                matching_items=row.matching_items,
                median_views=row.median_views,
                p90_views=row.p90_views,
                trend_slope_4wk_pct=row.trend_slope_4wk_pct,
                rationale=row.rationale,
            )
        )
        for row in rows
    ]