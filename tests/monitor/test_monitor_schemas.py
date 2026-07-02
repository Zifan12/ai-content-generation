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
    verdict = StoryCraftVerdict(
        clear_desire=True,
        visible_turn=True,
        earned_payoff=True,
        emotion_physical_tell=True,
        notes="ok",
        failure_notes=None,
        would_watch=True,
    )
    assert verdict.passes is True


def test_verdict_fails_when_any_dim_false() -> None:
    verdict = StoryCraftVerdict(
        clear_desire=True,
        visible_turn=True,
        earned_payoff=True,
        emotion_physical_tell=True,
        notes="meh",
        failure_notes="weak turn",
        would_watch=False,
    )
    assert verdict.passes is False
