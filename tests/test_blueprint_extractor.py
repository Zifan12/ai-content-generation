from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.blueprints.extractor import BlueprintExtractor
from src.blueprints.schema import Blueprint, EXTRACTOR_VERSION
from src.models.trend import RawContentItem


def _fake_blueprint() -> Blueprint:
    return Blueprint(
        format="talking_head",
        hook_type="shocking_claim",
        payoff_type="reveal",
        structure=["hook", "reveal", "cta"],
        primary_emotion="surprise",
        duration_band="10_20s",
        hook_strength=0.8,
        curiosity_gap=0.7,
        immediate_clarity=0.6,
        emotional_charge=0.7,
        payoff_quality=0.8,
        replayability=0.5,
        comment_trigger=0.4,
        shareability=0.6,
        extractor_version=EXTRACTOR_VERSION,
        extractor_model="claude-sonnet-4-6",
        confidence=0.8,
    )


def _item() -> RawContentItem:
    return RawContentItem(
        id=42,
        platform="tiktok",
        platform_content_id="vid42",
        url="https://tt.com/v/42",
        views=100_000,
        likes=10_000,
        comments=500,
        shares=200,
        hashtags=["mythology", "epic"],
        duration_in_seconds=22,
        content_format="video",
        description="Did you know Zeus had 100 children??",
        author_username="@mythguy",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_extract_calls_llm_with_envelope():
    """Extractor builds text envelope and calls AnthropicLLM.parse with Blueprint schema."""
    fake_llm = MagicMock()
    fake_llm.parse.return_value = _fake_blueprint() # Mock parse() to return a predictable Blueprint for this test
    extractor = BlueprintExtractor(llm=fake_llm)

    result = extractor.extract(item=_item(), transcript_text="Zeus was the king of the gods")

    assert isinstance(result, Blueprint)
    fake_llm.parse.assert_called_once()
    call_kwargs = fake_llm.parse.call_args.kwargs
    assert call_kwargs["response_model"] is Blueprint
    # Envelope contains key signals
    assert "Zeus had 100 children" in call_kwargs["prompt"]
    assert "Zeus was the king" in call_kwargs["prompt"]
    assert "@mythguy" in call_kwargs["prompt"]
    assert "22" in call_kwargs["prompt"]  # duration

def test_extract_handles_missing_transcript():
    fake_llm = MagicMock()
    fake_llm.parse.return_value = _fake_blueprint()
    extractor = BlueprintExtractor(llm=fake_llm)
    
    extractor.extract(item=_item(), transcript_text=None)

    call_kwargs = fake_llm.parse.call_args.kwargs 
    prompt = call_kwargs["prompt"].lower()
    # When transcript missing, envelope should mark it explicitly so LLM lowers confidence
    assert "transcript" in prompt
    assert "(missing)" in prompt


def test_extract_returns_blueprint_unchanged():
    """Make sure that the Extractor does not alter the Blueprint returned by the LLM"""
    fake_llm = MagicMock()
    expected_blueprint = _fake_blueprint()
    fake_llm.parse.return_value = expected_blueprint
    extractor = BlueprintExtractor(llm=fake_llm)

    result = extractor.extract(item=_item(), transcript_text="hello")  # Any text is fine here; this test only checks pass-through behavior.

    assert result is expected_blueprint
    assert result.model_dump() == expected_blueprint.model_dump()





