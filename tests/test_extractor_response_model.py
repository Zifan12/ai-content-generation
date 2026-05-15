import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.extractor_response import ExtractorResponse
from src.models.trend import RawContentItem
import src.models.niche
import src.models.blueprint
import src.models.eval
import src.models.transcript


@pytest.fixture
def db():
    """
    In-memory SQLite session with all tables created from the ORM metadata.

    Each test gets a fresh database — no state leaks between tests.
    Yields the session; tears down engine after the test completes.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def raw_item(db):
    """
    Minimal RawContentItem row satisfying FK requirement for ExtractorResponse.
    """
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="test_vid_001",
        url="https://www.tiktok.com/@x/video/test_vid_001",
    )
    db.add(item)
    db.flush()
    return item


def _make_response(item_id: int, fingerprint: str = "abc123") -> ExtractorResponse:
    """Build a valid ExtractorResponse for the given item id and fingerprint."""
    return ExtractorResponse(
        content_item_id=item_id,
        prompt_fingerprint=fingerprint,
        system_prompt="You are an expert analyst.",
        envelope="Caption: surreal void. Duration: 15s.",
        raw_response={"hook_type": "visual_shock", "pacing": "slow_atmospheric"},
        model="claude-sonnet-4-6",
        usage_input_tokens=500,
        usage_output_tokens=200,
        usage_cache_read_tokens=450,
        usage_cache_write_tokens=300,
    )


def test_write_and_read_roundtrip(db, raw_item):
    """Row written to DB reads back with all fields intact, including JSON payload."""
    row = _make_response(raw_item.id, fingerprint="fp_roundtrip")
    db.add(row)
    db.commit()

    result = db.query(ExtractorResponse).filter_by(prompt_fingerprint="fp_roundtrip").one()
    assert result.content_item_id == raw_item.id
    assert result.model == "claude-sonnet-4-6"
    assert result.raw_response == {"hook_type": "visual_shock", "pacing": "slow_atmospheric"}
    assert result.usage_input_tokens == 500
    assert result.usage_output_tokens == 200
    assert result.usage_cache_read_tokens == 450
    assert result.usage_cache_write_tokens == 300
    assert result.created_at is not None


def test_unique_constraint_same_item_same_fingerprint(db, raw_item):
    """Two rows with identical (content_item_id, prompt_fingerprint) raise IntegrityError."""
    db.add(_make_response(raw_item.id, fingerprint="fp_dupe"))
    db.commit()

    db.add(_make_response(raw_item.id, fingerprint="fp_dupe"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_different_fingerprint_same_item_allowed(db, raw_item):
    """Same item, different fingerprints = two rows allowed (prompt evolution)."""
    db.add(_make_response(raw_item.id, fingerprint="fp_v1"))
    db.add(_make_response(raw_item.id, fingerprint="fp_v2"))
    db.commit()

    rows = db.query(ExtractorResponse).filter_by(content_item_id=raw_item.id).all()
    assert len(rows) == 2


def test_nullable_usage_columns(db, raw_item):
    """Rows with all usage_* columns as None insert and read back cleanly."""
    row = ExtractorResponse(
        content_item_id=raw_item.id,
        prompt_fingerprint="fp_no_usage",
        system_prompt="sys",
        envelope="env",
        raw_response={},
        model="claude-sonnet-4-6",
        usage_input_tokens=None,
        usage_output_tokens=None,
        usage_cache_read_tokens=None,
        usage_cache_write_tokens=None,
    )
    db.add(row)
    db.commit()

    result = db.query(ExtractorResponse).filter_by(prompt_fingerprint="fp_no_usage").one()
    assert result.usage_input_tokens is None
    assert result.usage_output_tokens is None
    assert result.usage_cache_read_tokens is None
