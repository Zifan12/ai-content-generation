import argparse
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.enrichment.transcripts import TranscriptFetcher
from src.models.transcript import Transcript
from src.models.trend import RawContentItem


def find_unprocessed(db: Session, limit: int) -> list[RawContentItem]:
    """Return RawContentItem rows with subtitle_url set but no Transcript row yet.

    Args:
        db: Active SQLAlchemy session.
        limit: Max number of rows to return.

    Returns:
        List of unprocessed RawContentItem rows, ordered by DB insertion order.
    """
    # rows where subtitle_url IS NOT NULL and no Transcript exists
    stmt = (
        select(RawContentItem)
        .outerjoin(Transcript, Transcript.content_item_id == RawContentItem.id)
        .where(Transcript.id.is_(None))
        .where(RawContentItem.subtitle_url.is_not(None))
        .limit(limit)
    )

    return list(db.scalars(stmt).all())

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Fetch transcripts for unprocessed rows.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    db = SessionLocal()

    try:
        items = find_unprocessed(db, args.limit)
        print(f"Found {len(items)} items missing transcripts.")
        fetcher = TranscriptFetcher(db)
        success = 0
        for item in items:
            result = fetcher.fetch_one(item)
            if result:
                success += 1
        print(f"Transcribed {success}/{len(items)}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()