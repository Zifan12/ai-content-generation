"""
Niche metadata — content categories and search seeds.

PIPELINE ROLE:
  Define niches → seed scraper search queries → assign to RawContentItem → scope analysis

WHY THIS FILE EXISTS:
  Niches partition the content universe. Each niche has:
  - keywords: search terms for scraper (e.g., ["surreal", "hyperreal", "uncanny"])
  - hashtag_seeds: popular hashtags to track (e.g., ["#surrealism", "#hyperrealism"])
  - is_active: toggle on/off without deleting
  
  Niches are **runtime parameters**, not architectural primitives (as of 2026-05-10 reframe).
  They can be added/modified via DB or YAML without code changes.

CURRENT NICHES (surreal_hyperreal focus, P1 test fixture):
  - surreal_hyperreal: photorealistic impossible/uncanny content (primary test niche)
  - brainrot, anime_ai, horror_ai: retained for ablation testing only

FUTURE:
  Closed-loop (P3.5) will post generated videos to TikTok test accounts scoped
  by niche. This drives niche-specific Blueprint extraction (P1.5 foundation).
"""

from sqlalchemy import Boolean, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Niche(Base):
    """
    Content niche — category with associated search keywords and hashtags.
    
    Fields:
      name: unique identifier (e.g., 'surreal_hyperreal')
      keywords: list[str] for scraper search queries
      hashtag_seeds: list[str] to seed trending-hashtag analysis
      is_active: toggle niche on/off for scraping
    """
    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    hashtag_seeds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)