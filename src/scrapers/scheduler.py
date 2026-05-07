"""
APScheduler glue that runs one TikTok scrape per active niche on a 24h cycle.

Lives outside the scrapers themselves so the schedule can change without
touching scraper code, and so FastAPI's lifespan can start/stop it cleanly.
"""

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import SessionLocal
from src.scrapers.tiktok import TikTokScraper
from src.models.niche import Niche

scheduler = AsyncIOScheduler()

async def scrape_tiktok(hashtags: list[str], niche_id: int):
    """
    Run one TikTok scrape job for the given niche, swallowing exceptions so a
    single failure does not abort the scheduler loop.
    """
    db = SessionLocal()
    try:
        scraper = TikTokScraper(db)
        await scraper.fetch_trending(max_results=30, niche_id=niche_id, query=hashtags)
    except Exception as e:
        print(f"[scheduler] tiktok scrape failed ({hashtags}): {e}")
    finally:
        db.close()

def start():
    """Register one 24h job per active niche with seeds, then start the scheduler loop."""
    db = SessionLocal()
    try:
        niches = db.query(Niche).filter(Niche.is_active == True).all()
        for niche in niches:
            if niche.hashtag_seeds:
                # next_run_time=now forces immediate first run; without it APScheduler
                # waits a full 24h before firing.
                scheduler.add_job(scrape_tiktok, "interval", hours=24, args=[niche.hashtag_seeds, niche.id], next_run_time=datetime.now(timezone.utc))
    finally:
        db.close()
    scheduler.start()

def stop():
    scheduler.shutdown()