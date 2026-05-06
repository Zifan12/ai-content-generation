import math

from src.blueprints.schema import EXTRACTOR_VERSION
from src.evals.blueprint_eval import schema_valid_rate
from src.models.blueprint import BlueprintRecord


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
