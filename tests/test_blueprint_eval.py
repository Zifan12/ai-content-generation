import math
import pytest
from src.blueprints.schema import EXTRACTOR_VERSION
from src.evals.blueprint_eval import schema_valid_rate
from src.models.blueprint import BlueprintRecord
from src.evals.blueprint_eval import cohen_kappa_pairs, mae_pairs


def _good_payload() -> dict:
    return {
        "format": "talking_head",
        "format_subtype": None,
        "hook_type": "shocking_claim",
        "hook_subtype": None,
        "payoff_type": "reveal",
        "payoff_subtype": None,
        "structure": ["hook", "reveal", "cta"],
        "primary_emotion": "surprise",
        "duration_band": "10_20s",
        "hook_strength": 0.8,
        "curiosity_gap": 0.7,
        "immediate_clarity": 0.6,
        "emotional_charge": 0.7,
        "payoff_quality": 0.8,
        "replayability": 0.5,
        "comment_trigger": 0.4,
        "shareability": 0.6,
        "extractor_version": EXTRACTOR_VERSION,
        "extractor_model": "claude-sonnet-4-6",
        "confidence": 0.8,
        "notes": None,
    }


def _record(payload: dict) -> BlueprintRecord:
    return BlueprintRecord(
        content_item_id=1,
        extractor_version=EXTRACTOR_VERSION,
        extractor_model=payload["extractor_model"],
        confidence=payload["confidence"],
        blueprint_data=payload
    )

def test_schema_valid_rate_all_valid():
    records = [_record(_good_payload()) for _ in range(3)]
    assert schema_valid_rate(records) == 1.0

def test_schema_valid_rate_partial():
    good_records = [_record(_good_payload()) for _ in range(2)]
    bad_payload = _good_payload()
    bad_payload["primary_emotion"] = "nope" # invalid enum
    bad_record = _record(bad_payload)
    records = good_records + [bad_record]
    assert schema_valid_rate(records) == 2 / 3

def test_schema_valid_rate_empty_returns_nan():
    records = []
    assert math.isnan(schema_valid_rate(records))

def test_cohen_kappa_perfect_agreement():
    a = ["talking_head", "stitch", "demo"]
    b = ["talking_head", "stitch", "demo"]
    assert cohen_kappa_pairs(a, b) == 1.0

def test_cohen_kappa_total_disagreement():
    a = ["talking_head", "stitch", "demo"]
    b = ["stitch", "demo", "talking_head"]
    # All paired differently → kappa near 0 or negative
    assert cohen_kappa_pairs(a, b) <= 0.0

def test_cohen_kappa_empty_returns_nan():
    assert math.isnan(cohen_kappa_pairs([], []))

def test_mae_pairs_zero_when_identical():
    a = [0.5, 0.7, 0.3]
    b = [0.5, 0.7, 0.3]
    assert mae_pairs(a, b) == 0.0


def test_mae_pairs_nonzero():
    a = [0.5, 0.7, 0.3]
    b = [0.4, 0.9, 0.5]
    # |0.1| + |0.2| + |0.2| = 0.5 / 3 ≈ 0.1667
    assert mae_pairs(a, b) == pytest.approx(0.5 / 3)


def test_mae_pairs_empty_returns_nan():
    assert math.isnan(mae_pairs([], []))