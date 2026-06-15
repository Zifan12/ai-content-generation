"""
Tests for the P3.5 publish CLIs: record_post and enter_views (the manual-source seam).

Uses the same in-memory SQLite fixture pattern as test_published_video_model.py. The CLI logic
functions take a session passed in, so they are exercised directly here without a subprocess.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.blueprint import BlueprintRecord
from src.models.published_video import PublishedVideo
from scripts.record_post import record_post
from scripts.enter_views import enter_views


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
    bp = BlueprintRecord(
        content_item_id=1,
        extractor_version="v3",
        extractor_model="test-model",
        blueprint_data={"niche_label": "surreal_hyperreal"},
    )
    db.add(bp)
    db.commit()
    return bp


def test_record_post_creates_row_with_null_counts(db):
    bp = _make_blueprint(db)
    pv = record_post(db, blueprint_id=bp.id, tiktok_url="https://www.tiktok.com/@me/video/1")

    assert pv.id is not None
    assert pv.blueprint_id == bp.id
    assert pv.niche == "surreal_hyperreal"
    assert pv.view_7d is None
    assert pv.fetched_at is None


def test_record_post_persists_to_db(db):
    bp = _make_blueprint(db)
    record_post(db, blueprint_id=bp.id, tiktok_url="https://www.tiktok.com/@me/video/2")

    found = db.query(PublishedVideo).filter_by(tiktok_url="https://www.tiktok.com/@me/video/2").one()
    assert found.blueprint_id == bp.id


def test_enter_views_by_id_sets_counts_and_fetched_at(db):
    bp = _make_blueprint(db)
    pv = record_post(db, blueprint_id=bp.id, tiktok_url="https://www.tiktok.com/@me/video/3")

    updated = enter_views(db, post_id=pv.id, views=842, likes=30, comments=5, shares=2)

    assert updated.view_7d == 842
    assert updated.like_7d == 30
    assert updated.comment_7d == 5
    assert updated.share_7d == 2
    assert updated.fetched_at is not None


def test_enter_views_by_url(db):
    bp = _make_blueprint(db)
    record_post(db, blueprint_id=bp.id, tiktok_url="https://www.tiktok.com/@me/video/4")

    updated = enter_views(db, url="https://www.tiktok.com/@me/video/4", views=100)
    assert updated.view_7d == 100


def test_enter_views_requires_id_or_url(db):
    with pytest.raises(ValueError):
        enter_views(db, views=50)


def test_enter_views_missing_post_raises(db):
    with pytest.raises(ValueError):
        enter_views(db, post_id=99999, views=50)
