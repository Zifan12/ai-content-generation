"""Tests for the story-craft schema models (src/monitor/schemas.py, Stage B)."""
import pytest
from pydantic import ValidationError

from src.monitor.schemas import (
    BeatRole,
    CaptionPolicy,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryCraftVerdict,
    StoryPitch,
    StoryPitchSlate,
)


def _beat(
    role: BeatRole = BeatRole.hook,
    shot_size: ShotSize = ShotSize.wide,
    hero: bool = False,
) -> StoryBeat:
    return StoryBeat(
        role=role,
        visual_line="x",
        narration_line=None,
        shot_size=shot_size,
        characters_in_frame=["Eve"],
        hero_moment=hero,
    )


def _pitch(**overrides: object) -> StoryPitch:
    defaults = {
        "logline": "x",
        "mode": ContentMode.wish,
        "characters": [CharacterRef(name="Eve", ip_source="Stellar Blade")],
        "desired_moment": "x",
        "beats": [
            _beat(BeatRole.hook, ShotSize.wide),
            _beat(BeatRole.turn, ShotSize.medium),
            _beat(BeatRole.payoff, ShotSize.close_up, hero=True),
        ],
        "caption_policy": CaptionPolicy.hook_only,
        "hook_line": "the ending they owed us",
        "why_it_lands": "x",
        "legal_flag": False,
    }
    defaults.update(overrides)
    return StoryPitch(**defaults)


def test_dialogue_requires_speaker() -> None:
    with pytest.raises(ValidationError):
        StoryBeat(
            role=BeatRole.turn,
            visual_line="x",
            narration_line=None,
            dialogue_line="Wait, don't!",
            speaker=None,
            shot_size=ShotSize.medium,
            characters_in_frame=["Eve"],
            hero_moment=False,
        )


def test_speaker_must_be_in_characters_in_frame() -> None:
    with pytest.raises(ValidationError):
        StoryBeat(
            role=BeatRole.turn,
            visual_line="x",
            narration_line=None,
            dialogue_line="Wait, don't!",
            speaker="Ghost",
            shot_size=ShotSize.medium,
            characters_in_frame=["Eve"],
            hero_moment=False,
        )


def test_valid_dialogue_beat_constructs() -> None:
    beat = StoryBeat(
        role=BeatRole.turn,
        visual_line="x",
        narration_line=None,
        dialogue_line="Wait, don't!",
        speaker="Eve",
        shot_size=ShotSize.medium,
        characters_in_frame=["Eve"],
        hero_moment=False,
    )
    assert beat.dialogue_line == "Wait, don't!"
    assert beat.speaker == "Eve"


def test_silent_beat_defaults_dialogue_and_speaker_none() -> None:
    beat = _beat()
    assert beat.dialogue_line is None
    assert beat.speaker is None


def test_six_beats_now_rejected() -> None:
    with pytest.raises(ValidationError):
        _pitch(
            beats=[
                _beat(BeatRole.hook, ShotSize.wide),
                _beat(BeatRole.establish, ShotSize.establishing),
                _beat(BeatRole.build, ShotSize.medium),
                _beat(BeatRole.turn, ShotSize.over_shoulder),
                _beat(BeatRole.reveal, ShotSize.close_up),
                _beat(BeatRole.payoff, ShotSize.extreme_close_up, hero=True),
            ]
        )


def test_five_beats_still_valid() -> None:
    pitch = _pitch(
        beats=[
            _beat(BeatRole.hook, ShotSize.wide),
            _beat(BeatRole.establish, ShotSize.establishing),
            _beat(BeatRole.turn, ShotSize.medium),
            _beat(BeatRole.reveal, ShotSize.over_shoulder),
            _beat(BeatRole.payoff, ShotSize.close_up, hero=True),
        ]
    )
    assert len(pitch.beats) == 5


def test_scene_setting_defaults_empty_string_for_backcompat() -> None:
    pitch = _pitch()
    assert pitch.scene_setting == ""


def test_old_six_beat_story_json_row_now_invalid_by_design() -> None:
    """
    Pins the documented behavior (spec §6 BACK-COMPAT note): a pre-v2 stored
    row with 6 beats is now format-obsolete. The loader (smoke_content_writer's
    resolve_pitch) treats a ValidationError here as "re-pitch this event",
    never as a silent downgrade.
    """
    old_row = {
        # a minimal 6-beat pre-v2 story_json shape
        "logline": "x", "mode": "wish",
        "characters": [{"name": "Eve", "ip_source": "SB"}],
        "desired_moment": "x",
        "beats": [
            {"role": r, "visual_line": "x", "narration_line": None,
             "shot_size": "medium", "characters_in_frame": ["Eve"],
             "hero_moment": r == "payoff"}
            for r in ["hook", "establish", "build", "turn", "reveal", "payoff"]
        ],
        "caption_policy": "hook_only", "hook_line": "x",
        "why_it_lands": "x", "legal_flag": False,
    }
    with pytest.raises(ValidationError):
        StoryPitch.model_validate(old_row)


def _verdict(**overrides: object) -> StoryCraftVerdict:
    defaults = dict(
        clear_desire=True,
        visible_turn=True,
        earned_payoff=True,
        emotion_physical_tell=True,
        cold_viewer_legible=True,
        kinetic_payoff=True,
        register_match=True,
        dialogue_earns_place=True,
        scene_setting_contained=True,
        one_action_per_beat=True,
        notes="ok",
        failure_notes=None,
        would_watch=True,
    )
    defaults.update(overrides)
    return StoryCraftVerdict(**defaults)


def test_verdict_passes_when_all_nine_dims_true() -> None:
    assert _verdict().passes is True


def test_verdict_fails_when_any_new_dim_false() -> None:
    assert _verdict(cold_viewer_legible=False).passes is False
    assert _verdict(kinetic_payoff=False).passes is False
    assert _verdict(register_match=False).passes is False
    assert _verdict(dialogue_earns_place=False).passes is False
    assert _verdict(scene_setting_contained=False).passes is False
    assert _verdict(one_action_per_beat=False).passes is False


def test_character_ref_defaults_needs_reference_true() -> None:
    assert CharacterRef(name="Eve", ip_source="Stellar Blade").needs_reference is True


def test_valid_pitch_constructs() -> None:
    pitch = _pitch()
    assert len(pitch.beats) == 3
    assert pitch.caption_policy is CaptionPolicy.hook_only


def test_all_same_shot_size_rejected() -> None:
    with pytest.raises(ValidationError):
        _pitch(
            beats=[
                _beat(BeatRole.hook, ShotSize.wide),
                _beat(BeatRole.turn, ShotSize.wide),
                _beat(BeatRole.payoff, ShotSize.wide, hero=True),
            ]
        )


def test_two_hero_moments_rejected() -> None:
    with pytest.raises(ValidationError):
        _pitch(
            beats=[
                _beat(BeatRole.hook, ShotSize.wide, hero=True),
                _beat(BeatRole.turn, ShotSize.medium),
                _beat(BeatRole.payoff, ShotSize.close_up, hero=True),
            ]
        )


def test_hook_only_requires_hook_line() -> None:
    with pytest.raises(ValidationError):
        _pitch(caption_policy=CaptionPolicy.hook_only, hook_line=None)


def test_hook_line_without_hook_only_rejected() -> None:
    with pytest.raises(ValidationError):
        _pitch(caption_policy=CaptionPolicy.none, hook_line="stray line")


def test_beats_below_minimum_rejected() -> None:
    with pytest.raises(ValidationError):
        _pitch(
            beats=[
                _beat(BeatRole.hook, ShotSize.wide),
                _beat(BeatRole.turn, ShotSize.medium),
            ]
        )


def test_slate_requires_two_to_three_pitches() -> None:
    with pytest.raises(ValidationError):
        StoryPitchSlate(pitches=[_pitch()])
    slate = StoryPitchSlate(pitches=[_pitch(), _pitch()])
    assert len(slate.pitches) == 2


def test_verdict_passes_when_all_true() -> None:
    assert _verdict().passes is True


def test_verdict_fails_when_any_dim_false() -> None:
    assert _verdict(would_watch=False).passes is False
