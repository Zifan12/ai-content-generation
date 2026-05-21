
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
import src.miner.storage  # noqa: F401 — registers MinerRanking with Base

from src.miner.storage import persist_run, latest_run
from src.miner.schemas import BlueprintCandidate, MinerEvidence



@pytest.fixture
def db():
    """In-memory SQLite session, fresh per test. Mirrors fixture in test_extractor_response_model.py."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()

def test_round_trip(db):
    evidence = MinerEvidence(
        matching_items=1,
        median_views=1000,
        p90_views=5000,
        trend_slope_4wk_pct=0.1,
        rationale="test"
    )
    candidate1 = BlueprintCandidate(
        rank=1,
        niche_label="test",
        blueprint_template={"hook_type": "visual_shock"},
        evidence=evidence,
    )

    candidate2 = BlueprintCandidate(
        rank=2,
        niche_label="test",
        blueprint_template={"hook_type": "visual_shock"},
        evidence=evidence,
    )

    candidate3 = BlueprintCandidate(
        rank=3,
        niche_label="test",
        blueprint_template={"hook_type": "visual_shock"},
        evidence=evidence,
    )

    candidate4 = BlueprintCandidate(
        rank=4,
        niche_label="test",
        blueprint_template={"hook_type": "visual_shock"},
        evidence=evidence,
    )

    candidate5 = BlueprintCandidate(
        rank=5,
        niche_label="test",
        blueprint_template={"hook_type": "visual_shock"},
        evidence=evidence,
    )

    candidates = [candidate1, candidate2, candidate3, candidate4, candidate5]
    persist_run(db, candidates=candidates, niche_label="test")
    result = latest_run(db, niche_label="test")
    assert len(result) == 5
    assert result == candidates