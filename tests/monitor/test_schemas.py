import pytest
from pydantic import ValidationError
from src.monitor.schemas import (
    GapAnalysis,
    GapType,
    AnglePitch,
    AnglePitchSlate,
)


def _make_pitch() -> AnglePitch:
    return AnglePitch(
        take="Render the tower falling",
        format_description="Wide shot, handheld chaos, 8s",
        render_backend="visual_satire",
        estimated_cost_credits=2.0,
        gap_satisfaction_rationale="Delivers the wish-fulfillment moment",
        legal_flag=False,
    )


def test_GapAnalysis():
    gap = GapAnalysis(
        dominant_emotion="anger",
        audience_want="the violent climax they never got",
        gap_type="alternate_reality",
        producibility_score=4.0,
        virality_window_hours=38.0,
        reasoning="audience explicitly asked for this in comments",
    )
    assert gap.gap_type == GapType.alternate_reality
    assert gap.producibility_score == 4.0


def test_invalid_gap_type():
    # all other fields valid — the ONLY thing wrong is gap_type, so the
    # ValidationError can only be coming from the enum check.
    with pytest.raises(ValidationError):
        GapAnalysis(
            dominant_emotion="anger",
            audience_want="the violent climax they never got",
            gap_type="REJECT",
            producibility_score=4.0,
            virality_window_hours=38.0,
            reasoning="audience explicitly asked for this in comments",
        )


def test_extra_field_DNE():
    with pytest.raises(ValidationError):
        GapAnalysis(
            dominant_emotion="anger",
            audience_want="the violent climax they never got",
            gap_type="alternate_reality",
            producibility_score=4.0,
            virality_window_hours=38.0,
            reasoning="audience explicitly asked for this in comments",
            mood="cheerful",
        )


def test_angle_pitch_slate_requires_three():

    pitch1 = _make_pitch()
    pitch2 = _make_pitch()
    pitch3 = _make_pitch()

    with pytest.raises(ValidationError):
        AnglePitchSlate(angles=[pitch1, pitch2])

    assert AnglePitchSlate(angles=[pitch1, pitch2, pitch3])
