import asyncio
from dotenv import load_dotenv

load_dotenv("config/.env")

from src.database import SessionLocal
from src.scrapers.tiktok import TikTokScraper


async def main():
    db = SessionLocal()
    try:
        scraper = TikTokScraper(db)
        print("Starting TikTok scrape...")
        items = await scraper.fetch_trending(max_results=10, query="gymtok")
        print(f"Saved {len(items)} items to DB")
        for item in items:
            print(f"  [{item.platform_content_id}] views={item.views} likes={item.likes} hashtags={item.hashtags[:3]}")
    finally:
        db.close()


asyncio.run(main())
