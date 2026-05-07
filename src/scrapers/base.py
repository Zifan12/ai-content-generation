"""
Abstract base for platform scrapers.

Defines the `fetch_trending` contract every scraper must implement and
provides `save_items` so per-platform code never deals with SQLAlchemy
unique-constraint handling.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
