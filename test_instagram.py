import asyncio
from dotenv import load_dotenv

load_dotenv("config/.env")

from src.database import SessionLocal
from src.scrapers.instagram import InstagramScraper


async def main():
    db = SessionLocal()
    try:
        scraper = InstagramScraper(db)
        print("Starting Instagram scrape...")
        # Pass a real username — actor doesn't support keyword search
        items = await scraper.fetch_trending(max_results=20, query="instagram")
        print(f"Saved {len(items)} items to DB")
        for item in items:
            print(f"  [{item.platform_content_id}] views={item.views} likes={item.likes}")
    finally:
        db.close()


asyncio.run(main())
