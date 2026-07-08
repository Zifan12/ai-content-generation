import pytest
from pydantic import ValidationError
from src.monitor.schemas import GapAnalysis, PlanDecision


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


def test_plan_decision_next_url_defaults_empty():
    decision = PlanDecision(next_action="reddit_search", next_query="some query")
    assert decision.next_url == ""


def test_plan_decision_accepts_firecrawl_extract_action():
    decision = PlanDecision(
        next_action="firecrawl_extract",
        next_query="",
        next_url="https://example.com/wiki/X",
    )
    assert decision.next_action == "firecrawl_extract"
    assert decision.next_url == "https://example.com/wiki/X"
