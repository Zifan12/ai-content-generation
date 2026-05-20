"""
Abstract base for platform scrapers.

Defines the `fetch_trending` contract every scraper must implement and
provides `save_items` so per-platform code never deals with SQLAlchemy
unique-constraint handling.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.models.trend import RawContentItem



class BaseScraper(ABC):
    """
    Common interface for all platform scrapers.
    """

    platform: str

    def __init__(self, db: Session):
        self.db = db
    
    @abstractmethod
    async def fetch_trending(self, max_results: int=20, niche_id: int | None = None, query: str | None = None) -> list[RawContentItem]:
        """Fetch and persist trending content for a platform."""
        pass

    def save_items(self, items: Sequence[RawContentItem]) -> list[RawContentItem]:
        """
        Persist items individually, swallowing per-row IntegrityError on the
        (platform, platform_content_id) unique constraint so duplicate scrapes
        skip rather than abort the batch. Returns only successfully saved rows.
        """
        saved: list[RawContentItem] = []
        
        for item in items:
            try:
                self.db.add(item)
                self.db.commit()
                self.db.refresh(item)
                saved.append(item)
            except IntegrityError:
                self.db.rollback()
                # Duplicate on unique constraint (platform, platform_content_id)
                continue
        return saved
    
    def upsert_items(self, items: Sequence[RawContentItem]) -> tuple[int, int]:
        """
        Persist items using INSERT OR UPDATE semantics on (platform, platform_content_id).

        On conflict, mutable engagement fields (views, likes, comments, shares,
        collect_count, collected_at) are overwritten with fresh values. Immutable
        identity/content fields (published_at, url, hashtags, author_*, etc.) are
        left unchanged.

        Args:
            items: RawContentItem instances to persist.

        Returns:
            Tuple of (inserted_count, updated_count). Sum equals len(items) —
            every item either inserts or updates, no skips.
        """
        inserted = 0
        updated = 0
        mutable_fields = ["likes", "views", "comments", "shares", "collect_count"]

        for item in items:
            exists = (
                self.db.query(RawContentItem)
                .filter_by(platform=item.platform, platform_content_id=item.platform_content_id)
                .first()
            )

            values = {col.name: getattr(item, col.name) for col in RawContentItem.__table__.columns if col.name not in ("id", "collected_at", "created_at")}
            values["collected_at"] = func.now()

            set_ = {k: v for k, v in values.items() if k in mutable_fields}
            stmt = (
                sqlite_insert(RawContentItem.__table__)
                .values(values)
                .on_conflict_do_update(index_elements=["platform", "platform_content_id"], set_=set_)
            )
            
            self.db.execute(stmt)
            self.db.commit()

            if exists:
                updated += 1
            else:
                inserted += 1
        
        return inserted, updated