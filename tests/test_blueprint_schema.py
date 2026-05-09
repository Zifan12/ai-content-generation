import pytest
from pydantic import ValidationError

from src.blueprints.schema import Blueprint, EXTRACTOR_VERSION


def _valid_payload() -> dict:
    return {
        "format": "talking_head",  # v0: open string
        "format_subtype": None,
        "hook_type": "shocking_claim",
        "hook_subtype": None,
        "payoff_type": "reveal",
        "payoff_subtype": None,
        "structure": ["hook", "tension", "reveal", "cta"],
        "primary_emotion": "surprise",
        "duration_band": "10_20s",
        "hook_strength": 0.8,
        "curiosity_gap": 0.7,
        "immediate_clarity": 0.6,
        "emotional_charge": 0.75,
        "payoff_quality": 0.85,
        "replayability": 0.4,
        "comment_trigger": 0.3,
        "shareability": 0.6,
        "extractor_version": EXTRACTOR_VERSION,
        "extractor_model": "claude-sonnet-4-6",
        "confidence": 0.8,
        "notes": None,
    }


def test_valid_payload_parses():
    bp = Blueprint(**_valid_payload())
    assert bp.format == "talking_head"
    assert bp.structure == ["hook", "tension", "reveal", "cta"]

def test_format_rejects_unknown_value_in_v1():
    """v1 format is closed Literal — unknown values raise ValidationError."""
    payload = _valid_payload()
    payload["format"] = "weird_unknown_format_xyz"
    with pytest.raises(ValidationError):
        Blueprint(**payload) 

def test_invalid_structure_value_rejected():
    payload = _valid_payload()
    payload["structure"] = ["hook", "alien_stage", "cta"]
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_invalid_emotion_rejected():
    payload = _valid_payload()
    payload["primary_emotion"] = "ennui"
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_invalid_duration_band_rejected():
    payload = _valid_payload()
    payload["duration_band"] = "5_minutes"
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_mechanic_above_one_rejected():
    payload = _valid_payload()
    payload["hook_strength"] = 1.5
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_mechanic_below_zero_rejected():
    payload = _valid_payload()
    payload["curiosity_gap"] = -0.1
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_confidence_above_one_rejected():
    payload = _valid_payload()
    payload["confidence"] = 1.2
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_subtype_optional():
    payload = _valid_payload()
    payload["format_subtype"] = "podcast_cut"
    bp = Blueprint(**payload)
    assert bp.format_subtype == "podcast_cut"

