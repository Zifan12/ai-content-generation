
from dotenv import load_dotenv
load_dotenv("config/.env")
import asyncio
from src.observability import flush

class FakeDB:
    def add(self, item): pass
    def commit(self): pass
    def refresh(self, item): pass

async def main():
    from src.scrapers.youtube import YoutubeScraper
    scraper = YoutubeScraper(db=FakeDB())
    results = await scraper.fetch_trending(max_results=3, query="cooking")
    print(f"Got {len(results)} items")
    flush()

asyncio.run(main())
