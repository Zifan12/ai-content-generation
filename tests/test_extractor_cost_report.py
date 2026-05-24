"""
Tests for the --dry-run cost estimator in scripts/extractor_cost_report.py.

Verifies that dry_run_estimate computes median per-call cost from cached
ExtractorResponse rows and scales it by N future calls, without ever
constructing an Anthropic SDK client (ADR-0005 pre-flight gate).
"""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.extractor_response import ExtractorResponse
from src.models.niche import Niche
from src.models.trend import RawContentItem

# Side-effect imports so Base.metadata sees every table before create_all().
import src.models.blueprint  # noqa: F401
import src.models.eval  # noqa: F401
import src.models.transcript  # noqa: F401

from scripts.extractor_cost_report import dry_run_estimate


@pytest.fixture
def db():
    """In-memory SQLite session, fresh per test. Mirrors fixture in test_extractor_response_model.py."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def seed_extraction(
    db,
    niche_name: str,
    input_tokens: int = 3000,
    output_tokens: int = 1500,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> ExtractorResponse:
    """Create Niche (if new), RawContentItem, and ExtractorResponse linked together.

    Uses unique platform_content_id per row by counting existing items so test data
    doesn't collide on the unique constraint.
    """
    niche = db.execute(select(Niche).filter_by(name=niche_name)).scalar_one_or_none()
    if niche is None:
        niche = Niche(name=niche_name, keywords=[], hashtag_seeds=[])
        db.add(niche)
        db.flush()

    existing_count = db.execute(select(func.count()).select_from(RawContentItem)).scalar_one()
    item = RawContentItem(
        platform="tiktok",
        platform_content_id=f"test_{existing_count}",
        url=f"https://tiktok.com/test_{existing_count}",
        niche_id=niche.id,
        views=1000,
        likes=100,
        comments=10,
        shares=5,
    )
    db.add(item)
    db.flush()

    resp = ExtractorResponse(
        content_item_id=item.id,
        prompt_fingerprint=f"fp_{existing_count}",
        system_prompt="test",
        envelope="test",
        raw_response={},
        model="claude-sonnet-4-6",
        usage_input_tokens=input_tokens,
        usage_output_tokens=output_tokens,
        usage_cache_read_tokens=cache_read_tokens,
        usage_cache_write_tokens=cache_write_tokens,
    )
    db.add(resp)
    db.commit()
    return resp


def test_dry_run_returns_expected_keys_and_correct_math(db):
    """Happy path: 3 identical rows → median equals the single per-call cost, estimate scales linearly."""
    for _ in range(3):
        seed_extraction(db, "test_niche", input_tokens=3000, output_tokens=1500)

    result = dry_run_estimate(db, future_n=10, niche_name=None)

    assert set(result.keys()) == {
        "sample_size",
        "future_n",
        "niche",
        "median_cost_per_call_usd",
        "estimated_usd",
    }
    assert result["sample_size"] == 3
    assert result["future_n"] == 10
    assert result["niche"] is None

    # Per-call cost: 3000 * $3/M + 1500 * $15/M = 0.009 + 0.0225 = 0.0315
    expected_per_call = 3000 / 1_000_000 * 3.00 + 1500 / 1_000_000 * 15.00
    assert result["median_cost_per_call_usd"] == pytest.approx(expected_per_call)
    assert result["estimated_usd"] == pytest.approx(expected_per_call * 10)


def test_dry_run_raises_on_empty_db(db):
    """Empty extractor_responses → RuntimeError, since dry-run requires a populated cache."""
    with pytest.raises(RuntimeError, match="No extractor_responses rows found"):
        dry_run_estimate(db, future_n=10, niche_name=None)


def test_dry_run_raises_when_niche_filter_matches_nothing(db):
    """Niche filter applied to a non-existent niche → empty result → RuntimeError."""
    seed_extraction(db, "alpha")
    with pytest.raises(RuntimeError, match="for niche 'nonexistent'"):
        dry_run_estimate(db, future_n=10, niche_name="nonexistent")


def test_dry_run_filter_by_niche_narrows_sample(db):
    """Seed 2 niches with different row counts → niche filter restricts sample_size accordingly."""
    for _ in range(2):
        seed_extraction(db, "alpha")
    for _ in range(3):
        seed_extraction(db, "beta")

    result_alpha = dry_run_estimate(db, future_n=1, niche_name="alpha")
    result_beta = dry_run_estimate(db, future_n=1, niche_name="beta")
    result_all = dry_run_estimate(db, future_n=1, niche_name=None)

    assert result_alpha["sample_size"] == 2
    assert result_alpha["niche"] == "alpha"
    assert result_beta["sample_size"] == 3
    assert result_beta["niche"] == "beta"
    assert result_all["sample_size"] == 5


def test_dry_run_constructs_no_anthropic_client(db, monkeypatch):
    """Dry-run must work with no ANTHROPIC_API_KEY set — proves no SDK instantiation."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    seed_extraction(db, "test_niche")

    # Should complete without raising. If the function ever instantiated AnthropicLLM,
    # the missing key would surface here.
    result = dry_run_estimate(db, future_n=5, niche_name=None)
    assert result["sample_size"] == 1
    assert result["estimated_usd"] > 0
