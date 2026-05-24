"""
Scrape TikTok trending content via Apify actor.

PIPELINE ROLE:
  → Scrape (this file) → Trend analysis → Label → Blueprint extraction → RAG/Generation

WHY THIS SCRIPT EXISTS:
  Bootstraps the content corpus from TikTok. Runs Apify's tiktok-scraper actor
  (cost: ~$0.30 per 1K items) on niche keywords + hashtags. Stores raw content
  in RawContentItem table with full audit trail (raw_apify_payload).

WORKFLOW:
  1. Query niches table (or use --niche flag)
  2. Build startUrls from keywords + hashtag_seeds
  3. Call Apify actor with startUrls, limit, sort_type
  4. Normalize response via TikTokScraper._normalize_item()
  5. Save to RawContentItem (unique constraint prevents duplicates)
  6. Print counts (new vs duplicates)

FLAGS:
  --niche NAME          Scrape only this niche (default: all active niches)
  --limit N             Max items per niche (default: 50)
  --keywords K1 K2...   Custom keywords (overrides niche.keywords)
  --sort-type TYPE      Ranking: RELEVANCE (default), MOST_LIKED, DATE_POSTED
  --no-hashtags         Skip hashtag startUrls, keywords only

COST:
  ~$0.30 per 1000 items via Apify Starter plan.
  Track usage in config/providers.yaml [apify_starter].
"""

import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from sqlalchemy import select

from src.database import SessionLocal
from src.models.niche import Niche
from src.scrapers.tiktok import TikTokScraper

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / "config" / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main():
    """
    CLI entry point. Parse args, then scrape niches.
    """
    parser = argparse.ArgumentParser(description="Scrape TikTok trending content.")
    parser.add_argument("--niche", type=str, default=None, help="Niche name to scrape (default: all active niches)")
    parser.add_argument("--limit", type=int, default=50, help="Max items per scrape run")
    parser.add_argument("--keywords", type=str, nargs="*", default=None, help="Keyword search terms (sortType applies to these)")
    parser.add_argument("--sort-type", type=str, default="RELEVANCE", choices=["RELEVANCE", "MOST_LIKED", "DATE_POSTED"], help="Sort order for keyword results")
    parser.add_argument("--no-hashtags", action="store_true", help="Skip hashtag startUrls, use keywords only")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.niche:
            niches = db.execute(
                select(Niche).where(Niche.name == args.niche, Niche.is_active == True)
            ).scalars().all()
            if not niches:
                log.error(f"Niche '{args.niche}' not found or not active")
                return
        else:
            niches = db.execute(select(Niche).where(Niche.is_active == True)).scalars().all()

        scraper = TikTokScraper(db=db)

        for niche in niches:
            hashtag_seeds = [] if args.no_hashtags else niche.hashtag_seeds
            log.info(f"Scraping niche={niche.name} limit={args.limit} sort={args.sort_type} hashtags={len(hashtag_seeds)} keywords={len(args.keywords or [])}")
            items, inserted, updated = await scraper.fetch_trending(
                max_results=args.limit,
                niche_id=niche.id,
                query=hashtag_seeds,
                keywords=args.keywords,
                sort_type=args.sort_type,
            )
            log.info(f"{niche.name}: {inserted} new items saved | {updated} items updated")


if __name__ == "__main__":
    asyncio.run(main())
