"""Task 10 — verify the smoke script's --pitch-id handoff path.

Two behaviors are pinned:
  1. resolve_premise_and_model(--pitch-id) loads the approved AnglePitchRecord and
     returns its ``take`` as the premise plus the backend-derived motion model.
  2. --pitch-id and --premise are mutually exclusive at the argparse layer.

The resolver takes the DB session as an argument, so these run against an in-memory
SQLite fixture with no Postgres and no LLM/render calls.
"""

import argparse
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.smoke_content_writer import _build_parser, resolve_premise_and_model
from src.database import Base
from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    # Create only the two tables this test touches — importing the smoke script
    # registers Postgres-only models (pgvector) on Base that SQLite can't build.
    Base.metadata.create_all(
        engine,
        tables=[TrendingEventRecord.__table__, AnglePitchRecord.__table__],
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _seed_approved_pitch(db, *, take: str, backend: str = "visual_satire") -> AnglePitchRecord:
    """Insert a parent event + one approved angle pitch and return the pitch."""
    event = TrendingEventRecord(
        run_at=datetime.now(timezone.utc),
        source="reddit",
        headline="Dragon spotted circling Tokyo Tower at dawn",
        reaction_sample="I wish we got to see it actually breathe fire.",
        trendiness_score=0.92,
        virality_window_hours=18.0,
        selected_for_pitching=True,
    )
    db.add(event)
    db.flush()

    pitch = AnglePitchRecord(
        trending_event_id=event.id,
        take=take,
        format_description="Single wide aerial shot, slow push-in as flame erupts",
        render_backend=backend,
        estimated_cost_credits=24.0,
        gap_satisfaction_rationale="Shows the fire-breath payoff fans were denied",
        legal_flag=False,
        approved=True,
    )
    db.add(pitch)
    db.flush()
    return pitch


def test_pitch_id_feeds_take_as_premise(db):
    pitch = _seed_approved_pitch(
        db, take="The dragon finally breathes fire over Tokyo Tower at dawn"
    )
    args = argparse.Namespace(pitch_id=pitch.id, premise=None, model="veo3_1")

    premise, model_cli_id = resolve_premise_and_model(args, db)

    assert premise == pitch.take
    assert model_cli_id == "veo3_1"


def test_pitch_id_and_premise_are_mutually_exclusive():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--pitch-id", "1", "--premise", "manual override"])
