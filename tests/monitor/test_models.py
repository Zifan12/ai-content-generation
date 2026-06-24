from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.trending_event import TrendingEventRecord
from src.models.angle_pitch import AnglePitchRecord
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


def _make_event(db) -> TrendingEventRecord:
    """Insert a minimal valid TrendingEventRecord for use as a parent FK."""
    event = TrendingEventRecord(
        run_at=datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc),
        source="reddit",
        headline="Fans furious over Boys S5 finale letdown",
        reaction_sample="where was the rampage they promised us",
        trendiness_score=0.87,
        virality_window_hours=36.0,
    )
    db.add(event)
    db.commit()
    return event


def test_trending_event_round_trip(db):
    """TrendingEventRecord persists required fields; gap-agent nullable fields default to None."""
    event = _make_event(db)

    fetched = db.query(TrendingEventRecord).filter_by(id=event.id).one()
    assert fetched.id is not None
    assert fetched.source == "reddit"
    assert fetched.headline == "Fans furious over Boys S5 finale letdown"
    assert fetched.trendiness_score == pytest.approx(0.87)
    assert fetched.virality_window_hours == pytest.approx(36.0)
    assert fetched.selected_for_pitching is False
    # gap-agent fields filled later — must be null at insert
    assert fetched.dominant_emotion is None
    assert fetched.audience_want is None
    assert fetched.gap_type is None
    assert fetched.producibility_score is None
    assert fetched.composite_score is None


def test_angle_pitch_fk_round_trip(db):
    """AnglePitchRecord persists with a valid trending_event_id FK; approved is null until reviewed."""
    event = _make_event(db)

    pitch = AnglePitchRecord(
        trending_event_id=event.id,
        take="Render the violent rampage fans were denied — show the tower falling",
        format_description="Single wide shot, handheld chaos, dusk lighting, no dialogue, 8s",
        render_backend="visual_satire",
        estimated_cost_credits=2.0,
        gap_satisfaction_rationale="Delivers the wish-fulfillment moment the audience wanted",
        legal_flag=False,
    )
    db.add(pitch)
    db.commit()

    fetched = db.query(AnglePitchRecord).filter_by(id=pitch.id).one()
    assert fetched.trending_event_id == event.id
    assert fetched.render_backend == "visual_satire"
    assert fetched.legal_flag is False
    # not reviewed yet
    assert fetched.approved is None
    assert fetched.approved_at is None


def test_published_video_has_news_reactive_columns(db):
    """PublishedVideo schema includes all five news-reactive columns added in Task 2."""
    column_names = PublishedVideo.__table__.columns.keys()
    assert "angle_pitch_id" in column_names
    assert "trendiness_score_at_post" in column_names
    assert "gap_type" in column_names
    assert "format_backend" in column_names
    assert "virality_window_hours_remaining" in column_names
