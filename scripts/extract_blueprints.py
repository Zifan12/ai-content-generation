import argparse
import logging
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

from src.blueprints.extractor import BlueprintExtractor  # noqa: E402
from src.blueprints.schema import EXTRACTOR_VERSION, Blueprint  # noqa: E402
from src.database import SessionLocal  # noqa: E402
from src.models.blueprint import BlueprintRecord  # noqa: E402
from src.models.transcript import Transcript  # noqa: E402
from src.models.trend import RawContentItem  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

def find_unprocessed(db: Session, version: str, niche_id: int | None, limit: int)  -> list[RawContentItem]:
    """Return RawContentItems that have no Blueprint row at `version`.
    
    Uses a NOT EXISTS / NOT IN subquery against the blueprints table
    filtered by extractor_version = version. Optionally filter by niche_id.
    Caps at `limit` rows.
    """

    # video IDs that already have a blueprint for this version
    have_blueprint = (
        select(BlueprintRecord.content_item_id)
        .where(BlueprintRecord.extractor_version == version)
    )

    stmt = (
        select(RawContentItem)
        .where(RawContentItem.id.not_in(have_blueprint))
    )

    if niche_id is not None:
        stmt = stmt.where(RawContentItem.niche_id == niche_id)

    stmt = stmt.limit(limit)

    return list(db.scalars(stmt))

def get_transcript_text(db: Session, content_item_id: int) -> str | None:
    """Return plain transcript text for a content item, or None if no Transcript row exists."""

    stmt = (
        select(Transcript.text)
        .where(Transcript.content_item_id == content_item_id)
    )
    return db.scalar(stmt)

def save_blueprint(db: Session, content_item_id: int, blueprint: Blueprint, version: str, confidence: float, model: str) -> None:
    """Insert a BlueprintRecord row for the given content item and commit.

    Args:
        db: Active SQLAlchemy session.
        content_item_id: FK to raw_content_items.id.
        blueprint: Extracted Blueprint Pydantic object — serialized to dict for JSON storage.
        version: Extractor version string (e.g. "v0").
        confidence: Extraction confidence score from the LLM response.
        model: Model ID used for extraction (e.g. "claude-sonnet-4-5").
    """
    record = BlueprintRecord(
        content_item_id=content_item_id,
        extractor_version=version,
        extractor_model=model,
        confidence=confidence,
        blueprint_data=blueprint.model_dump(),
    )

    db.add(record)
    db.commit()

def main() -> None:
    """
    Parses CLI args, fetches unprocessed RawContentItems, 
    extracts a Blueprint for each via LLM and saves result to the database.
    """
    parser = argparse.ArgumentParser(description="Extract blueprints for unprocessed rows.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--niche-id", type=int, default=None)
    parser.add_argument("--extractor-version", type=str, default=EXTRACTOR_VERSION)
    args = parser.parse_args()

    db = SessionLocal()

    try:
        items = find_unprocessed(db, args.extractor_version, args.niche_id, args.limit)
        extractor = BlueprintExtractor()
        successes: list[float] = []
        failures = 0

        for item in items:
            try:
                text = get_transcript_text(db, item.id)
                bp = extractor.extract(item, text)
                successes.append(bp.confidence)
                save_blueprint(db, item.id, bp, args.extractor_version, bp.confidence, extractor.llm.model)
                log.info(f"item {item.id} confidence={bp.confidence}")
            except Exception as e:
                log.error(f"item {item.id} failed {e}")
                db.rollback()
                failures += 1
                continue
        log.info("Done. Succeeded: %d, Failed: %d", len(successes), failures)
        if successes:
            log.info("Mean confidence: %.3f", mean(successes))
    
    finally:
        db.close()


if __name__ == "__main__":
    main()