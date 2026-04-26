"""
One-shot script: seed initial niches into the DB.
Run: uv run python scripts/seed_niches.py
Safe to re-run — skips niches that already exist (unique constraint on name).

Prerequisites: Run Alembic migrations before using this script:
  uv run alembic upgrade head
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv("config/.env")

from src.database import SessionLocal  # noqa: E402
from src.models.niche import Niche  # noqa: E402

NICHES = [
    {
        "name": "brainrot",
        "keywords": ["absurd", "surreal", "mashup", "weird", "brainrot"],
        "hashtag_seeds": ["italianbrainrot", "brainrot", "aigenerated", "weirdai", "aianimation"],
        "is_active": True,
    },
    {
        "name": "anime_ai",
        "keywords": ["anime", "ghibli", "manga", "animation", "art"],
        "hashtag_seeds": ["aianimation", "ghibliart", "animestyle", "aiart", "mangafilter"],
        "is_active": True,
    },
    {
        "name": "horror_ai",
        "keywords": ["horror", "dark", "scary", "truecrime", "creepy"],
        "hashtag_seeds": ["horrortok", "aihorror", "darkstories", "scarystories", "truecrime"],
        "is_active": True,
    },
]

def seed():
    db = SessionLocal()
    added = 0
    skipped = 0
    try:
        for data in NICHES:
            existing = db.query(Niche).filter(Niche.name == data["name"]).first()
            if existing:
                print(f"  skip (exists): {data['name']}")
                skipped += 1
                continue
            niche = Niche(**data)
            db.add(niche)
            db.commit()
            print(f"  added: {data['name']} — seeds: {data['hashtag_seeds']}")
            added += 1
    finally:
        db.close()
    print(f"\nDone. Added: {added}, Skipped: {skipped}")


if __name__ == "__main__":
    seed()
