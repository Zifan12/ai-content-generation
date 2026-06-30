import pytest
from pydantic import ValidationError

from src.blueprints.schema import Blueprint, EXTRACTOR_VERSION


def _valid_payload() -> dict:
    return {
        "hook_type": "visual_shock",
        "hook_subtype": "unsettling_reveal",
        "primary_emotion": "awe",
        "share_hook_type": "technical_awe",
        "comment_bait_type": "question_to_viewer",
        "pacing": "moderate",
        "loop_type": "seamless_visual",
        "audio_type": "music_only",
        "visual_complexity": "dense",
        "color_mood": "vivid_saturated",
        "duration_band": "10_20s",
        "aesthetic_descriptors": ["photorealistic", "impossible_physics", "uncanny"],
        "niche_label": "surreal_hyperreal",
        "extractor_version": EXTRACTOR_VERSION,
        "extractor_model": "claude-sonnet-5",
        "notes": None,
    }


def test_valid_payload_parses():
    bp = Blueprint(**_valid_payload())
    assert bp.hook_type == "visual_shock"
    assert bp.primary_emotion == "awe"
    assert bp.niche_label == "surreal_hyperreal"
    assert bp.aesthetic_descriptors == ["photorealistic", "impossible_physics", "uncanny"]

def test_hook_type_rejects_unlocked_value():
    """v3.1: hook_type is Literal-locked; invented values must raise ValidationError (ADR-0003)."""
    payload = _valid_payload()
    payload["hook_type"] = "slow_reveal_uncanny"
    with pytest.raises(ValidationError):
        Blueprint(**payload)

def test_primary_emotion_rejects_unknown_value():
    payload = _valid_payload()
    payload["primary_emotion"] = "ennui"
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_invalid_duration_band_rejected():
    payload = _valid_payload()
    payload["duration_band"] = "5_minutes"
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_aesthetic_descriptors_must_be_list_of_strings():
    payload = _valid_payload()
    payload["aesthetic_descriptors"] = "not_a_list"
    with pytest.raises(ValidationError):
        Blueprint(**payload)


def test_aesthetic_descriptors_can_hold_arbitrary_strings():
    payload = _valid_payload()
    payload["aesthetic_descriptors"] = ["chaotic", "italian_brainrot", "absurdist"]
    bp = Blueprint(**payload)
    assert bp.aesthetic_descriptors == ["chaotic", "italian_brainrot", "absurdist"]


def test_niche_label_accepts_arbitrary_string():
    payload = _valid_payload()
    payload["niche_label"] = "some_new_niche_we_just_invented"
    bp = Blueprint(**payload)
    assert bp.niche_label == "some_new_niche_we_just_invented"


def test_blueprint_round_trips_via_json():
    bp = Blueprint(**_valid_payload())
    payload = bp.model_dump_json()
    bp2 = Blueprint.model_validate_json(payload)
    assert bp == bp2


def test_hook_subtype_optional():
    payload = _valid_payload()
    payload["hook_subtype"] = "unsettling_reveal"
    bp = Blueprint(**payload)
    assert bp.hook_subtype == "unsettling_reveal"


def test_no_legacy_v1_fields_present():
    bp = Blueprint(**_valid_payload())
    dumped = bp.model_dump()
    for legacy_field in [
        "format",
        "format_subtype",
        "payoff_type",
        "payoff_subtype",
        "structure",
        "hook_strength",
        "curiosity_gap",
        "immediate_clarity",
        "emotional_charge",
        "payoff_quality",
        "replayability",
        "comment_trigger",
        "shareability",
        "confidence",
    ]:
        assert legacy_field not in dumped, f"Legacy v1 field present: {legacy_field}"

