import pytest
from pydantic import ValidationError
from src.miner.schemas import MinerEvidence
from src.miner.schemas import BlueprintCandidate



def test_matching_items_below_one(): 
    with pytest.raises(ValidationError):
        MinerEvidence(
            matching_items=0, # invalid — ge=1
            median_views=1000,
            p90_views=5000,
            trend_slope_4wk_pct=0.1,
            rationale="test"
        )

def test_round_trip():
    evidence = MinerEvidence(
        matching_items=1,
        median_views=1000,
        p90_views=5000,
        trend_slope_4wk_pct=0.1,
        rationale="test"
    )

    candidate = BlueprintCandidate(
        rank=9,
        niche_label="test",
        blueprint_template={"hook_type": "visual_shock"},
        evidence=evidence,
    )

    data = candidate.model_dump()
    reconstructed = BlueprintCandidate.model_validate(data)
    assert candidate == reconstructed


def test_empty_blueprint_template():
    evidence = MinerEvidence(
        matching_items=1,
        median_views=1000,
        p90_views=5000,
        trend_slope_4wk_pct=0.1,
        rationale="test"
    )

    with pytest.raises(ValidationError):
        BlueprintCandidate(rank=9, niche_label="test", blueprint_template={}, evidence=evidence)

def test_negative_slope_accepted():
    evidence = MinerEvidence(
        matching_items=1,
        median_views=1000,
        p90_views=5000,
        trend_slope_4wk_pct=-0.5,
        rationale="test"
    )

    assert evidence.trend_slope_4wk_pct == -0.5

