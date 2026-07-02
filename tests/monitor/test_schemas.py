import pytest
from pydantic import ValidationError
from src.monitor.schemas import (
    GapAnalysis,
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
        evidence_quotes=["they cut away right before the good part"],
        virality_window_hours=38.0,
        reasoning="audience explicitly asked for this in comments",
    )
    assert gap.evidence_quotes == ["they cut away right before the good part"]
    assert gap.dominant_emotion == "anger"


def test_evidence_quotes_default_empty():
    # evidence_quotes is optional and defaults to an empty list.
    gap = GapAnalysis(
        dominant_emotion="anger",
        audience_want="the violent climax they never got",
        virality_window_hours=38.0,
        reasoning="audience explicitly asked for this in comments",
    )
    assert gap.evidence_quotes == []


def test_too_many_evidence_quotes_rejected():
    # the schema caps evidence_quotes at 3; a 4th must fail validation.
    with pytest.raises(ValidationError):
        GapAnalysis(
            dominant_emotion="anger",
            audience_want="the violent climax they never got",
            evidence_quotes=["a", "b", "c", "d"],
            virality_window_hours=38.0,
            reasoning="audience explicitly asked for this in comments",
        )


def test_extra_field_DNE():
    with pytest.raises(ValidationError):
        GapAnalysis(
            dominant_emotion="anger",
            audience_want="the violent climax they never got",
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
