from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

from src.blueprints.extractor import BlueprintExtractor, compute_prompt_fingerprint, SYSTEM_PROMPT, build_envelope
from src.blueprints.schema import Blueprint, EXTRACTOR_VERSION
from src.database import Base
from src.models.extractor_response import ExtractorResponse
from src.models.trend import RawContentItem
import src.models.niche
import src.models.blueprint
import src.models.extractor_response
import src.models.eval
import src.models.transcript


mock_db = MagicMock()


@pytest.fixture
def db():
    """
    In-memory SQLite session with all tables created from the ORM metadata.

    Each test gets a fresh database — no state leaks between tests.
    Yields the session; tears down engine after the test completes.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


fake_raw = {
    "raw_response": {},
    "usage_input_tokens": 0,
    "usage_output_tokens": 0,
    "usage_cache_read_tokens": None,
}

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
    """Extractor builds text envelope and calls AnthropicLLM.parse_with_raw with Blueprint schema."""
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"
    expected_bp = _fake_blueprint()
    fake_llm.parse_with_raw.return_value = (expected_bp, fake_raw)
    extractor = BlueprintExtractor(llm=fake_llm)

    result = extractor.extract(
        item=_item(),
        transcript_text="Zeus was the king of the gods",
        niche_label="surreal_hyperreal",
        db=mock_db,
    )

    assert isinstance(result, Blueprint)
    fake_llm.parse_with_raw.assert_called_once()
    call_kwargs = fake_llm.parse_with_raw.call_args.kwargs
    assert call_kwargs["response_model"] is Blueprint
    # Envelope contains key signals
    assert "Zeus had 100 children" in call_kwargs["prompt"]
    assert "Zeus was the king" in call_kwargs["prompt"]
    assert "@mythguy" in call_kwargs["prompt"]
    assert "22" in call_kwargs["prompt"]  # duration
    assert "surreal_hyperreal" in call_kwargs["prompt"]

def test_extract_handles_missing_transcript():
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"
    expected_bp = _fake_blueprint()
    fake_llm.parse_with_raw.return_value = (expected_bp, fake_raw)
    extractor = BlueprintExtractor(llm=fake_llm)
    
    extractor.extract(item=_item(), transcript_text=None, niche_label="surreal_hyperreal", db=mock_db)

    call_kwargs = fake_llm.parse_with_raw.call_args.kwargs
    prompt = call_kwargs["prompt"].lower()
    # When transcript missing, envelope should mark it explicitly so LLM lowers confidence
    assert "transcript" in prompt
    assert "(missing)" in prompt


def test_extract_returns_blueprint_unchanged():
    """Make sure that the Extractor does not alter the Blueprint returned by the LLM"""
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"
    expected_bp = _fake_blueprint()
    fake_llm.parse_with_raw.return_value = (expected_bp, fake_raw)
    extractor = BlueprintExtractor(llm=fake_llm)

    result = extractor.extract(item=_item(), transcript_text="hello", niche_label="surreal_hyperreal", db=mock_db)  

    assert result is expected_bp
    assert result.model_dump() == expected_bp.model_dump()


def test_reparse_from_cache_hit_no_llm_call(db):
    item = _item()
    db.add(item)
    db.flush()
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"

    extractor = BlueprintExtractor(llm=fake_llm)
    envelope = build_envelope(item, None, "surreal_hyperreal")
    fake_fingerprint = compute_prompt_fingerprint(SYSTEM_PROMPT, envelope, "claude-sonnet-4-6", {"max_tokens": 2048})

    row = ExtractorResponse(
        content_item_id=item.id,
        prompt_fingerprint=fake_fingerprint,
        system_prompt = SYSTEM_PROMPT,
        envelope=envelope,
        raw_response=_fake_blueprint().model_dump(),
        model=fake_llm.model,
    )

    db.add(row)
    db.flush()

    result = extractor.reparse_from_cache(item, None, "surreal_hyperreal", db)
    assert isinstance(result, Blueprint)
    fake_llm.parse_with_raw.assert_not_called()


def test_reparse_from_cache_miss_different_fingerprint(db):
    item = _item()
    db.add(item)
    db.flush()
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"

    extractor = BlueprintExtractor(llm=fake_llm)
    envelope = build_envelope(item, None, "surreal_hyperreal")
    wrong_fingerprint = "a" * 64

    row = ExtractorResponse(
        content_item_id=item.id,
        prompt_fingerprint=wrong_fingerprint,
        system_prompt = SYSTEM_PROMPT,
        envelope=envelope,
        raw_response=_fake_blueprint().model_dump(),
        model=fake_llm.model,
    )

    db.add(row)
    db.flush()

    result = extractor.reparse_from_cache(item, None, "surreal_hyperreal", db)
    assert result is None
    fake_llm.parse_with_raw.assert_not_called()

def test_reparse_from_cache_hit_no_llm_call_invalid_raw_response(db):
    item = _item()
    db.add(item)
    db.flush()
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"

    extractor = BlueprintExtractor(llm=fake_llm)
    envelope = build_envelope(item, None, "surreal_hyperreal")
    fake_fingerprint = compute_prompt_fingerprint(SYSTEM_PROMPT, envelope, "claude-sonnet-4-6", {"max_tokens": 2048})

    row = ExtractorResponse(
        content_item_id=item.id,
        prompt_fingerprint=fake_fingerprint,
        system_prompt = SYSTEM_PROMPT,
        envelope=envelope,
        raw_response={},
        model=fake_llm.model,
    )

    db.add(row)
    db.flush()

    with pytest.raises(ValidationError):
        extractor.reparse_from_cache(item, None, "surreal_hyperreal", db)

def test_reparse_from_cache_no_cached_row(db):
    item = _item()
    db.add(item)
    db.flush()
    fake_llm = MagicMock()
    fake_llm.model = "claude-sonnet-4-6"

    extractor = BlueprintExtractor(llm=fake_llm)

    result = extractor.reparse_from_cache(item, None, "surreal_hyperreal", db)
    assert result is None
