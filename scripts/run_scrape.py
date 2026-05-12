import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from src.database import SessionLocal
from src.models.niche import Niche
from src.scrapers.tiktok import TikTokScraper

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / "config" / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Scrape TikTok trending content.")
    parser.add_argument("--niche", type=str, default=None, help="Niche name to scrape (default: all active niches)")
    parser.add_argument("--limit", type=int, default=50, help="Max items per scrape run")
    parser.add_argument("--keywords", type=str, nargs="*", default=None, help="Keyword search terms (sortType applies to these)")
    parser.add_argument("--sort-type", type=str, default="RELEVANCE", choices=["RELEVANCE", "MOST_LIKED", "DATE_POSTED"], help="Sort order for keyword results")
    parser.add_argument("--no-hashtags", action="store_true", help="Skip hashtag startUrls, use keywords only")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.niche:
            niches = db.query(Niche).filter(Niche.name == args.niche, Niche.is_active == True).all()
            if not niches:
                log.error(f"Niche '{args.niche}' not found or not active")
                return
        else:
            niches = db.query(Niche).filter(Niche.is_active == True).all()

        scraper = TikTokScraper(db=db)

        for niche in niches:
            hashtag_seeds = [] if args.no_hashtags else niche.hashtag_seeds
            log.info(f"Scraping niche={niche.name} limit={args.limit} sort={args.sort_type} hashtags={len(hashtag_seeds)} keywords={len(args.keywords or [])}")
            items = await scraper.fetch_trending(
                max_results=args.limit,
                niche_id=niche.id,
                query=hashtag_seeds,
                keywords=args.keywords,
                sort_type=args.sort_type,
            )
            log.info(f"{niche.name}: {len(items)} new items saved")


if __name__ == "__main__":
    asyncio.run(main())
