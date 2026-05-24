
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from src.models.niche import Niche
from src.models.trend import RawContentItem
from src.models.extractor_response import ExtractorResponse
from src.scrapers.recurring import run_niche_scrape, BudgetExceeded

from src.database import Base
import src.models.niche  # noqa: F401
import src.models.trend  # noqa: F401
import src.models.transcript  # noqa: F401
import src.models.blueprint  # noqa: F401
import src.models.extractor_response  # noqa: F401
import src.models.eval  # noqa: F401

from unittest.mock import patch, AsyncMock, MagicMock


def fake_extract(item, transcript, niche_label, db_arg):
    resp = ExtractorResponse(
        content_item_id=item.id,
        prompt_fingerprint=f"fp_{item.id}",
        system_prompt="test",
        envelope="test",
        raw_response={},
        model="claude-sonnet-4-6",
        usage_input_tokens=1000,
        usage_output_tokens=500,
        usage_cache_read_tokens=0,
        usage_cache_write_tokens=0,
    )
    db_arg.add(resp)
    db_arg.flush()
    return MagicMock()


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

def _make_factory(session):
    @contextmanager
    def factory():
        yield session
    return factory

def _seed_niche_and_items(db, niche_name, n_items):
    niche = db.execute(select(Niche).filter_by(name=niche_name)).scalar_one_or_none()
    if niche is None:
        niche = Niche(name=niche_name, keywords=[], hashtag_seeds=[])
        db.add(niche)
        db.flush()

    items = []
    for i in range(n_items):
        item = RawContentItem(
            platform="tiktok",
            platform_content_id=f"test_{i}",
            url=f"https://tiktok.com/test_{i}",
            niche_id=niche.id,
            views=1000,
            likes=100,
            comments=10,
            shares=5,
        )
        items.append(item)
        db.add(item)
    db.flush()

    return niche, items

@patch("src.scrapers.recurring.BlueprintExtractor.reparse_from_cache")
@patch("src.scrapers.recurring.TikTokScraper.fetch_trending", new_callable=AsyncMock)
def test_happy_path_all_cache_hits(mock_fetch, mock_reparse, db):
    niche, items = _seed_niche_and_items(db, "test_niche", 5)

    mock_fetch.return_value = (items, len(items), 0)
    mock_reparse.return_value = MagicMock()
    factory  = _make_factory(db)
    result = run_niche_scrape(niche.id, session_factory=factory)

    assert result["niche_name"] == "test_niche"
    assert result["items_scraped"] == 5
    assert result["items_inserted"] == 5
    assert result["items_cache_hit"] == 5
    assert result["items_extracted"] == 0
    assert result["extraction_usd_spent"] == 0.0
    assert result["error"] is None

@patch("src.scrapers.recurring.BlueprintExtractor.extract")
@patch("src.scrapers.recurring.BlueprintExtractor.reparse_from_cache")
@patch("src.scrapers.recurring.TikTokScraper.fetch_trending", new_callable=AsyncMock)
def test_mixed_cache_hits_and_misses(mock_fetch, mock_reparse, mock_extract, db):
    niche, items = _seed_niche_and_items(db, "test_niche", 5)
    mock_fetch.return_value = (items, len(items), 0)
    mock_reparse.side_effect = [MagicMock(), MagicMock(), MagicMock(), None, None]
    mock_extract.side_effect = fake_extract
    factory = _make_factory(db)
    result = run_niche_scrape(niche.id, session_factory=factory)

    assert result["items_cache_hit"] == 3
    assert result["items_extracted"] == 2
    assert result["extraction_usd_spent"] > 0
    assert abs(result["extraction_usd_spent"] - 0.021) < 0.0001
    assert result["error"] is None

@patch("src.scrapers.recurring.BlueprintExtractor.extract")
@patch("src.scrapers.recurring.BlueprintExtractor.reparse_from_cache")
@patch("src.scrapers.recurring.TikTokScraper.fetch_trending", new_callable=AsyncMock)
def test_budget_exceeded_raises_and_preserves_partial_counts(mock_fetch, mock_reparse, mock_extract, db, monkeypatch):
    monkeypatch.setattr("src.scrapers.recurring.DEFAULT_MAX_DAILY_SPEND", 0.001)
    niche, items = _seed_niche_and_items(db, "test_niche", 5)
    mock_fetch.return_value = (items, len(items), 0)
    mock_reparse.return_value = None
    mock_extract.side_effect = fake_extract
    factory = _make_factory(db)

    with pytest.raises(BudgetExceeded) as excinfo:
        run_niche_scrape(niche.id, session_factory=factory)

    partial = excinfo.value.partial_result

    assert partial["items_extracted"] >= 1
    assert partial["items_cache_hit"] == 0
    assert partial["extraction_usd_spent"] >= 0.001
    assert partial["completed_at"] != ""


@patch("src.scrapers.recurring.today_extraction_spend")
@patch("src.scrapers.recurring.BlueprintExtractor.extract")
@patch("src.scrapers.recurring.BlueprintExtractor.reparse_from_cache")
@patch("src.scrapers.recurring.TikTokScraper.fetch_trending", new_callable=AsyncMock)
def test_budget_guard_uses_db_spend(mock_fetch, mock_reparse, mock_extract, mock_today_spend, db):
    niche, items = _seed_niche_and_items(db, "test_niche", 2)
    mock_fetch.return_value = (items, 2, 0)
    mock_reparse.return_value = None
    mock_extract.side_effect = fake_extract
    mock_today_spend.side_effect = [0.999, 1.001]

    factory = _make_factory(db)

    with pytest.raises(BudgetExceeded) as excinfo:
        run_niche_scrape(niche.id, session_factory=factory)

    partial = excinfo.value.partial_result
    assert partial["items_extracted"] == 1