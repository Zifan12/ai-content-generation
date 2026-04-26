from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import SessionLocal
from src.scrapers.tiktok import TikTokScraper
from src.models.niche import Niche

scheduler = AsyncIOScheduler()

async def scrape_tiktok(hashtags: list[str], niche_id: int):
    db = SessionLocal()
    try:
        scraper = TikTokScraper(db)
        await scraper.fetch_trending(max_results=50, niche_id=niche_id, query=hashtags)
    except Exception as e:
        print(f"[scheduler] tiktok scrape failed ({hashtags}): {e}")
    finally:
        db.close()

def start():
    db = SessionLocal()
    try:
        niches = db.query(Niche).filter(Niche.is_active == True).all()
        for niche in niches:
            if niche.hashtag_seeds:
                scheduler.add_job(scrape_tiktok, "interval", hours=6, args=[niche.hashtag_seeds, niche.id], next_run_time=datetime.now(timezone.utc))
    finally:
        db.close()
    scheduler.start()

def stop():
    scheduler.shutdown()