"""
Tests for the P3.5 publish CLIs: record_post and enter_views (the manual-source seam).

Uses the same in-memory SQLite fixture pattern as test_published_video_model.py. The CLI logic
functions take a session passed in, so they are exercised directly here without a subprocess.
"""

import itertools

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.blueprint import BlueprintRecord
from src.models.published_video import PublishedVideo
from scripts.compute_percentiles import rank_percentiles, write_back_percentiles
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


_bp_counter = itertools.count(1)


def _make_blueprint(db) -> BlueprintRecord:
    # unique content_item_id per call — blueprints is UNIQUE on (content_item_id, extractor_version)
    bp = BlueprintRecord(
        content_item_id=next(_bp_counter),
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


def test_record_post_allows_null_blueprint_id(db):
    pv = record_post(db, blueprint_id=None, tiktok_url="https://www.tiktok.com/@me/video/exilus1")

    assert pv.id is not None
    assert pv.blueprint_id is None


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


# --- rank_percentiles math (pure, no DB) ---

def test_rank_percentiles_no_ties():
    # sorted [50, 100, 200]; positions 1, 0, 2 over (n-1)=2
    assert rank_percentiles([100, 50, 200]) == pytest.approx([0.5, 0.0, 1.0])


def test_rank_percentiles_with_ties():
    # sorted [50, 50, 100, 200]; the two 50s share avg rank 0.5 -> 0.5/3
    assert rank_percentiles([100, 50, 50, 200]) == pytest.approx(
        [2 / 3, 1 / 6, 1 / 6, 1.0]
    )


def test_rank_percentiles_single_value_is_neutral():
    assert rank_percentiles([42]) == [0.5]


def test_rank_percentiles_empty():
    assert rank_percentiles([]) == []


# --- write_back_percentiles (DB) ---

def test_write_back_percentiles_labels_blueprints(db):
    # three posts, each on its own blueprint, with distinct view counts
    specs = [(50, "v/a"), (200, "v/b"), (100, "v/c")]
    posts = []
    for views, url in specs:
        bp = _make_blueprint(db)
        pv = record_post(db, blueprint_id=bp.id, tiktok_url=url)
        enter_views(db, post_id=pv.id, views=views)
        posts.append((pv, bp))

    scored = write_back_percentiles(db)
    assert scored == 3

    # worst (50) -> 0.0, mid (100) -> 0.5, best (200) -> 1.0, written to each linked blueprint
    by_views = {pv.view_7d: bp for pv, bp in posts}
    db.refresh(by_views[50])
    db.refresh(by_views[100])
    db.refresh(by_views[200])
    assert by_views[50].outcome_view_percentile == pytest.approx(0.0)
    assert by_views[100].outcome_view_percentile == pytest.approx(0.5)
    assert by_views[200].outcome_view_percentile == pytest.approx(1.0)


def test_write_back_percentiles_skips_unmeasured(db):
    # a post with no view_7d must not be scored
    bp = _make_blueprint(db)
    record_post(db, blueprint_id=bp.id, tiktok_url="v/unmeasured")

    scored = write_back_percentiles(db)
    assert scored == 0
    db.refresh(bp)
    assert bp.outcome_view_percentile is None
