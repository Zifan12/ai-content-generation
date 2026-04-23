from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.trend import RawContentItem

class BaseScraper(ABC):
    """Common interface for all platform scrapers."""

    platform: str

    def __init__(self, db: Session):
        self.db = db
    
    @abstractmethod
    async def fetch_trending(self, max_results: int=20, niche_id: int | None = None, query: str | None = None) -> list[RawContentItem]:
        """Fetch and persist trending content for a platform."""
        pass

    def save_items(self, items: Sequence[RawContentItem]) -> list[RawContentItem]:
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
