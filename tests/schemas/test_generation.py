"""Tests for single-shot ContentPackage and Shot schemas (Task 1)."""

import pytest
from pydantic import ValidationError

from src.schemas.generation import ContentPackage, Shot


def _valid_shot() -> Shot:
    return Shot(
        start_keyframe="Handheld phone POV, kitchen counter, a glass of water mid-spill.",
        motion="Water freezes in place as it pours. Audio: sharp tap of ice forming.",
    )


def _valid_package() -> ContentPackage:
    return ContentPackage(
        shot=_valid_shot(),
        model_cli_id="veo3_1",
        premise="Water freezes mid-pour in a normal kitchen.",
        mood_anchor="Cool daylight, desaturated phone footage, photoreal, uncanny stillness.",
        onscreen_text=["wait is this real??"],
        caption="I still don't know what I filmed.",
        hashtags=["surreal", "fyp"],
    )


def test_content_package_round_trip_json():
    package = _valid_package()
    restored = ContentPackage.model_validate_json(package.model_dump_json())
    assert restored == package


def test_content_package_optional_defaults():
    package = _valid_package()
    assert package.voiceover is None
    assert package.grounding_hit_ids == []
    assert package.rationale is None


def test_shot_valid_without_end_keyframe():
    shot = Shot(
        start_keyframe="Wide shot, empty hallway.",
        motion="A door at the end swings open slowly. Audio: distant hinge creak.",
    )
    assert shot.end_keyframe is None


def test_shot_missing_motion_raises():
    with pytest.raises(ValidationError):
        Shot(start_keyframe="Close-up of a hand on a doorknob.")


def test_shot_missing_start_keyframe_raises():
    with pytest.raises(ValidationError):
        Shot(motion="The hand turns the knob. Audio: metal click.")


def test_old_shots_field_rejected():
    with pytest.raises(ValidationError):
        ContentPackage(
            shot=_valid_shot(),
            shots=[_valid_shot()],
            model_cli_id="veo3_1",
            premise="legacy shape",
            mood_anchor="test grade",
            onscreen_text=["hook"],
            caption="caption",
            hashtags=["tag"],
        )


def test_old_device_field_rejected():
    with pytest.raises(ValidationError):
        ContentPackage(
            shot=_valid_shot(),
            device="reveal",
            model_cli_id="veo3_1",
            premise="legacy shape",
            mood_anchor="test grade",
            onscreen_text=["hook"],
            caption="caption",
            hashtags=["tag"],
        )
