import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.models.trend import RawContentItem
from src.scrapers.tiktok import TikTokScraper

from src.database import Base
import src.models.niche  # noqa: F401
import src.models.trend  # noqa: F401
import src.models.transcript  # noqa: F401
import src.models.blueprint  # noqa: F401
import src.models.extractor_response  # noqa: F401
import src.models.eval  # noqa: F401

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


def test_upsert_inserts_new_item(db):

    scraper = TikTokScraper(db=db)
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="test_1",
        url="https://tiktok.com/test_1",
        views=1000,
        likes=100,
        comments=10, 
        shares=5,
        collect_count=0,
    )
    
    inserted, updated = scraper.upsert_items([item])

    assert (inserted, updated) == (1, 0)
    assert db.execute(select(RawContentItem).filter_by(platform_content_id="test_1")).scalar_one_or_none() is not None

def test_upsert_updates_existing_item(db):

    scraper = TikTokScraper(db=db)
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="test_1",
        url="https://tiktok.com/test_1",
        views=1000,
        likes=100,
        comments=10, 
        shares=5,
        collect_count=0,
    )

    item2 = RawContentItem(
        platform="tiktok",
        platform_content_id="test_1",
        url="https://tiktok.com/test_1",
        views=10000,
        likes=100,
        comments=10, 
        shares=5,
        collect_count=0,
)
    
    inserted, updated = scraper.upsert_items([item])
    assert (inserted, updated) == (1, 0)

    inserted, updated = scraper.upsert_items([item2])
    assert (inserted, updated) == (0, 1)
    row = db.execute(select(RawContentItem).filter_by(platform_content_id="test_1")).scalar_one_or_none()
    assert row.views == 10000
    assert db.execute(select(func.count()).select_from(RawContentItem)).scalar_one() == 1
