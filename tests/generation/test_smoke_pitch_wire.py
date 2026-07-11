"""Task 9 (partial) — verify the smoke script's --pitch-id story_json bridge.

Pinned behaviors:
  1. resolve_pitch(--pitch-id) loads the approved AnglePitchRecord, re-inflates
     ``story_json`` into a validated StoryPitch, and returns it with the id —
     the Stage-1 → Stage-2 bridge.
  2. A NULL story_json (pre-Stage-B legacy row) is a HARD SystemExit, never a
     silent fallback to the ``take`` logline (that path discarded the beats and
     defaulted every render to veo3_1 via the always-NULL render_backend column).
  3. The parser requires --pitch-id AND --refs (grounding mandatory).

The resolver takes the DB session as an argument, so these run against an
in-memory SQLite fixture with no Postgres and no LLM/render calls.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.smoke_content_writer import _build_parser, load_location, resolve_pitch
from src.database import Base
from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord
from src.monitor.schemas import StoryPitch
from tests.helpers.story_pitch import build_story_pitch


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


def _seed_pitch(db, *, story_json) -> AnglePitchRecord:
    """Insert a parent event + one approved pitch (story_json as given)."""
    event = TrendingEventRecord(
        run_at=datetime.now(timezone.utc),
        source="reddit",
        headline="Stellar Blade sequel reveal detonates the subreddit",
        reaction_sample="I wish we got the confrontation scene.",
        trendiness_score=0.92,
        virality_window_hours=18.0,
        selected_for_pitching=True,
    )
    db.add(event)
    db.flush()

    pitch = AnglePitchRecord(
        trending_event_id=event.id,
        take="Eve gets the ending the fans wanted.",
        estimated_cost_credits=45.0,
        gap_satisfaction_rationale="Renders the beat the reveal denied.",
        legal_flag=False,
        approved=True,
        story_json=story_json,
    )
    db.add(pitch)
    db.flush()
    return pitch


def test_resolve_pitch_reinflates_story_json(db):
    source = build_story_pitch(4)
    record = _seed_pitch(db, story_json=source.model_dump(mode="json"))
    args = argparse.Namespace(pitch_id=record.id)

    pitch, pitch_id = resolve_pitch(args, db)

    assert isinstance(pitch, StoryPitch)
    assert pitch_id == record.id
    assert len(pitch.beats) == 4
    assert pitch.hook_line == "the ending they cut"


def test_null_story_json_is_a_hard_error_not_a_fallback(db):
    record = _seed_pitch(db, story_json=None)
    args = argparse.Namespace(pitch_id=record.id)

    with pytest.raises(SystemExit, match="no story_json"):
        resolve_pitch(args, db)


def test_missing_pitch_row_exits_loudly(db):
    args = argparse.Namespace(pitch_id=999)
    with pytest.raises(SystemExit, match="No AnglePitchRecord"):
        resolve_pitch(args, db)


def test_parser_requires_pitch_id_and_refs():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--refs", "a.jpg"])  # no pitch-id
    with pytest.raises(SystemExit):
        parser.parse_args(["--pitch-id", "1"])  # no refs
    args = parser.parse_args(["--pitch-id", "1", "--refs", "a.jpg", "b.jpg"])
    assert args.pitch_id == 1
    assert args.refs == ["a.jpg", "b.jpg"]


# --- load_location: the --location slug -> (images, anchor text) resolver --------
# load_location builds refs/_location/<slug> from the cwd, so each test chdirs into
# a tmp dir and lays out the folder it expects.


def _make_location(tmp_path, slug, *, images=("room.jpg",), anchor="Ice-tower room."):
    """Create refs/_location/<slug>/ under tmp_path with the given images/anchor.

    Passing images=() or anchor=None omits that piece so the missing-file
    branches can be exercised.
    """
    folder = tmp_path / "refs" / "_location" / slug
    folder.mkdir(parents=True)
    for name in images:
        (folder / name).write_bytes(b"fake-image-bytes")
    if anchor is not None:
        (folder / "world_anchor.txt").write_text(anchor, encoding="utf-8")
    return folder


def test_load_location_returns_images_and_anchor(tmp_path, monkeypatch):
    _make_location(tmp_path, "elfie_bedroom", images=("b.png", "a.png"), anchor="Ice-tower room.\n")
    monkeypatch.chdir(tmp_path)

    images, anchor = load_location("elfie_bedroom")

    # images sorted by filename; paths use the OS separator (str(Path(...)));
    # anchor stripped of trailing whitespace
    base = Path("refs/_location/elfie_bedroom")
    assert images == [str(base / "a.png"), str(base / "b.png")]
    assert anchor == "Ice-tower room."


def test_load_location_missing_folder_exits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no refs/_location at all
    with pytest.raises(SystemExit, match="No location folder"):
        load_location("nope")


def test_load_location_no_image_exits(tmp_path, monkeypatch):
    _make_location(tmp_path, "empty_room", images=(), anchor="text")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="No image files"):
        load_location("empty_room")


def test_load_location_missing_anchor_text_exits(tmp_path, monkeypatch):
    _make_location(tmp_path, "no_anchor", images=("room.jpg",), anchor=None)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="No world_anchor.txt"):
        load_location("no_anchor")
