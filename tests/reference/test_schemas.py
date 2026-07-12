"""Tests for the reference harvester schemas (src/reference/schemas.py)."""
import pytest
from pydantic import ValidationError

from src.reference.schemas import (
    FrameScore,
    FrameVerdict,
    HarvestResult,
    QueryPlan,
    VideoCandidate,
    VideoPick,
)


def _candidate(**overrides: object) -> VideoCandidate:
    defaults = {
        "video_id": "abc123",
        "url": "https://youtube.com/watch?v=abc123",
        "title": "Trailer",
        "channel": "Official Channel",
        "duration_seconds": 90.0,
        "view_count": 1000,
        "description": "x",
        "transcript_excerpt": None,
    }
    defaults.update(overrides)
    return VideoCandidate(**defaults)


def _verdict(**overrides: object) -> FrameVerdict:
    defaults = {
        "character_present": True,
        "face_visibility": "clear",
        "text_or_watermark_overlap": False,
        "angle": "front",
        "single_character": True,
        "usable": True,
        "reason": "x",
    }
    defaults.update(overrides)
    return FrameVerdict(**defaults)


def test_query_plan_constructs_and_rejects_extra_field() -> None:
    plan = QueryPlan(queries=["a", "b", "c"], target_description="x")
    assert plan.queries == ["a", "b", "c"]
    with pytest.raises(ValidationError):
        QueryPlan(queries=["a", "b", "c"], target_description="x", extra="nope")


def test_query_plan_enforces_3_to_5_queries() -> None:
    with pytest.raises(ValidationError):
        QueryPlan(queries=["a", "b"], target_description="x")
    with pytest.raises(ValidationError):
        QueryPlan(queries=["a", "b", "c", "d", "e", "f"], target_description="x")


def test_video_candidate_constructs_and_rejects_extra_field() -> None:
    candidate = _candidate()
    assert candidate.video_id == "abc123"
    assert candidate.transcript_excerpt is None
    with pytest.raises(ValidationError):
        VideoCandidate(**{**_candidate().model_dump(), "extra": "nope"})


def test_video_pick_constructs_and_enforces_1_to_2_ids() -> None:
    pick = VideoPick(chosen_video_ids=["abc123"], reason="best match")
    assert pick.chosen_video_ids == ["abc123"]
    with pytest.raises(ValidationError):
        VideoPick(chosen_video_ids=[], reason="x")
    with pytest.raises(ValidationError):
        VideoPick(chosen_video_ids=["a", "b", "c"], reason="x")
    with pytest.raises(ValidationError):
        VideoPick(chosen_video_ids=["abc123"], reason="x", extra="nope")


def test_frame_verdict_constructs_and_rejects_extra_field() -> None:
    verdict = _verdict()
    assert verdict.usable is True
    with pytest.raises(ValidationError):
        FrameVerdict(**{**_verdict().model_dump(), "extra": "nope"})


def test_frame_verdict_rejects_bad_literal() -> None:
    with pytest.raises(ValidationError):
        _verdict(face_visibility="blurry")
    with pytest.raises(ValidationError):
        _verdict(angle="birds_eye")


def test_frame_score_defaults_verdict_none_and_rejects_extra_field() -> None:
    score = FrameScore(path="frame_001.png", sharpness=123.4)
    assert score.verdict is None
    score_with_verdict = FrameScore(
        path="frame_001.png", sharpness=123.4, verdict=_verdict()
    )
    assert score_with_verdict.verdict is not None
    with pytest.raises(ValidationError):
        FrameScore(path="x", sharpness=1.0, extra="nope")


def test_harvest_result_constructs_and_rejects_extra_field() -> None:
    result = HarvestResult(
        status="ok",
        character_name="Eve",
        approved_dir="data/reference_cache/eve",
        manifest_path="data/reference_cache/eve/manifest.json",
        detail="2 frames approved",
    )
    assert result.status == "ok"
    with pytest.raises(ValidationError):
        HarvestResult(**{**result.model_dump(), "extra": "nope"})


def test_harvest_result_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        HarvestResult(
            status="pending",
            character_name="Eve",
            approved_dir=None,
            manifest_path="x",
            detail="x",
        )
