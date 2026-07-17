"""Persistence tests for ExilusTopicRecord / TopicBrief (ticket 01).

Uses the same sqlite-in-memory fixture as tests/monitor/test_models.py — the
JSON column round-trips fine on sqlite, and there is no pgvector column on
this table, so a real Postgres connection buys nothing here.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.exilus_topic import ExilusTopicRecord
from src.monitor.schemas import BriefField, TopicBrief
from src.monitor.topic_brief import load_topic_brief, save_topic_brief


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _brief(marker: str) -> TopicBrief:
    return TopicBrief(
        identity=BriefField(content=f"identity {marker}", citations=["https://example.com/1"]),
        recent_events=BriefField(
            content=f"recent events {marker}", citations=["https://example.com/2"]
        ),
        key_characters=BriefField(
            content=f"key characters {marker}", citations=["https://example.com/3"]
        ),
        why_people_care=BriefField(
            content=f"why people care {marker}", citations=["https://example.com/4"]
        ),
        open_unknowns=[f"unknown {marker}"],
    )


def test_save_and_load_round_trips_equal_brief(db):
    brief = _brief("v1")

    save_topic_brief("Elfaria: Albis & Serfort", brief, db)
    fetched = load_topic_brief("Elfaria: Albis & Serfort", db)

    assert fetched == brief


def test_row_created_with_verified_brief_has_no_unverified_stamps(db):
    brief = _brief("v1")
    save_topic_brief("clean-topic", brief, db)

    fetched = load_topic_brief("clean-topic", db)

    assert fetched.identity.verified is True
    assert fetched.recent_events.verified is True
    assert fetched.key_characters.verified is True
    assert fetched.why_people_care.verified is True


def test_brief_with_unverified_field_persists_and_reloads(db):
    brief = _brief("v1")
    brief.recent_events.verified = False

    save_topic_brief("thin-topic", brief, db)
    fetched = load_topic_brief("thin-topic", db)

    assert fetched.recent_events.verified is False
    assert fetched.identity.verified is True


def test_second_save_replaces_rather_than_stacks(db):
    save_topic_brief("refresh-topic", _brief("v1"), db)
    save_topic_brief("refresh-topic", _brief("v2"), db)

    fetched = load_topic_brief("refresh-topic", db)

    assert fetched.identity.content == "identity v2"
    assert "v1" not in fetched.identity.content
    # still exactly one row for the topic — no duplicate stacked
    assert db.query(ExilusTopicRecord).filter_by(topic="refresh-topic").count() == 1


def test_load_unseen_topic_returns_none(db):
    assert load_topic_brief("never-researched", db) is None


def test_load_topic_row_with_no_brief_yet_returns_none(db):
    # a row can exist (e.g. a faction map written first) with brief_json
    # still NULL — that must read back as "no brief yet", not an error.
    row = ExilusTopicRecord(topic="faction-only-topic")
    db.add(row)
    db.commit()

    assert load_topic_brief("faction-only-topic", db) is None


def test_exilus_topic_record_table_has_expected_columns():
    column_names = ExilusTopicRecord.__table__.columns.keys()
    assert set(column_names) == {
        "id",
        "topic",
        "brief_json",
        "faction_map_json",
        "created_at",
        "updated_at",
    }
