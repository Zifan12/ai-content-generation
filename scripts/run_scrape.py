import asyncio
from pathlib import Path

from alembic.config import Config
from dotenv import load_dotenv

from alembic import command
from src.database import SessionLocal
from src.models.niche import Niche
from src.scrapers.tiktok import TikTokScraper

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"

load_dotenv(PROJECT_ROOT / "config" / ".env")

def run_migrations():
    cfg = Config(ALEMBIC_INI_PATH)
    command.upgrade(cfg, "head")


async def main():
    run_migrations()
    with SessionLocal() as db:
        niches = db.query(Niche).filter(Niche.is_active == True).all()
        scraper = TikTokScraper(db=db)

        for niche in niches:
            items = await scraper.fetch_trending(max_results=10, niche_id=niche.id, query=niche.hashtag_seeds)
            print(f"{niche.name}: {len(items)} saved")

if __name__ == "__main__":
    asyncio.run(main())
