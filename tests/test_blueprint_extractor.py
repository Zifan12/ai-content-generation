from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.blueprints.extractor import BlueprintExtractor
from src.blueprints.schema import Blueprint, EXTRACTOR_VERSION
from src.models.trend import RawContentItem


def _fake_blueprint() -> Blueprint:
    return Blueprint(
        hook_type="visual_shock",
        primary_emotion="awe",
        share_hook_type="technical_awe",
        comment_bait_type="question_to_viewer",
        pacing="fast",
        loop_type="seamless_visual",
        audio_type="original_voiceover",
        visual_complexity="dense",
        color_mood="desaturated",
        duration_band="10_20s",
        aesthetic_descriptors=["photorealistic", "liminal_space"],
        niche_label="surreal_hyperreal",
        hook_subtype=None,
        extractor_version=EXTRACTOR_VERSION,
        extractor_model="claude-sonnet-4-6",
        notes=None,
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

    result = extractor.extract(item=_item(), transcript_text="Zeus was the king of the gods", niche_label="surreal_hyperreal")

    assert isinstance(result, Blueprint)
    fake_llm.parse.assert_called_once()
    call_kwargs = fake_llm.parse.call_args.kwargs
    assert call_kwargs["response_model"] is Blueprint
    # Envelope contains key signals
    assert "Zeus had 100 children" in call_kwargs["prompt"]
    assert "Zeus was the king" in call_kwargs["prompt"]
    assert "@mythguy" in call_kwargs["prompt"]
    assert "22" in call_kwargs["prompt"]  # duration
    assert "surreal_hyperreal" in call_kwargs["prompt"]

def test_extract_handles_missing_transcript():
    fake_llm = MagicMock()
    fake_llm.parse.return_value = _fake_blueprint()
    extractor = BlueprintExtractor(llm=fake_llm)
    
    extractor.extract(item=_item(), transcript_text=None, niche_label="surreal_hyperreal")

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

    result = extractor.extract(item=_item(), transcript_text="hello", niche_label="surreal_hyperreal")  # Any text is fine here; this test only checks pass-through behavior.

    assert result is expected_blueprint
    assert result.model_dump() == expected_blueprint.model_dump()





