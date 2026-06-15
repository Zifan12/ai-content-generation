from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.blueprint import BlueprintRecord
from src.models.published_video import PublishedVideo


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _make_blueprint(db) -> BlueprintRecord:
    """
    Insert a minimal valid BlueprintRecord so a PublishedVideo can FK to it.

    content_item_id is itself an FK to raw_content_items, but SQLite does not enforce
    foreign keys by default, so a junk id commits fine in this in-memory test.
    """
    bp = BlueprintRecord(
        content_item_id=1,
        extractor_version="v3",
        extractor_model="test-model",
        blueprint_data={"niche_label": "surreal_hyperreal"},
    )
    db.add(bp)
    db.commit()
    return bp


def test_published_video_round_trip(db):
    """A PublishedVideo persists its fields and leaves count columns null until measured."""
    bp = _make_blueprint(db)

    pv = PublishedVideo(
        blueprint_id=bp.id,
        niche="surreal_hyperreal",
        tiktok_url="https://www.tiktok.com/@test/video/123",
        posted_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )
    db.add(pv)
    db.commit()

    fetched = db.query(PublishedVideo).filter_by(tiktok_url="https://www.tiktok.com/@test/video/123").one()
    assert fetched.id is not None
    assert fetched.blueprint_id == bp.id
    assert fetched.niche == "surreal_hyperreal"
    assert fetched.posted_at.year == 2026
    # counts are filled in a later manual pass, not at insert
    assert fetched.view_7d is None
    assert fetched.like_7d is None
    assert fetched.comment_7d is None
    assert fetched.share_7d is None
    assert fetched.fetched_at is None


def test_blueprint_has_outcome_percentile_column(db):
    """BlueprintRecord carries the P3.5 label column, defaulting to null."""
    bp = _make_blueprint(db)
    assert bp.outcome_view_percentile is None

    bp.outcome_view_percentile = 0.75
    db.commit()
    refetched = db.query(BlueprintRecord).filter_by(id=bp.id).one()
    assert refetched.outcome_view_percentile == 0.75
