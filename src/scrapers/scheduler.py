

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import SessionLocal
from src.scrapers.youtube import YoutubeScraper

scheduler = AsyncIOScheduler()

async def scrape_youtube():
    db = SessionLocal()
    try:
        scraper = YoutubeScraper(db)
        await scraper.fetch_trending(max_results=20)
    except Exception as e:
        print(f"[scheduler] scrape failed: {e}")
    finally:
        db.close()

def start():
    scheduler.add_job(scrape_youtube, "interval", hours=6)
    scheduler.start()

def stop():
    scheduler.shutdown()