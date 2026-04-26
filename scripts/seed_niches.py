"""
One-shot script: seed initial niches into the DB.
Run: uv run python scripts/seed_niches.py
Safe to re-run — skips niches that already exist (unique constraint on name).
"""
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv("config/.env")

from src.database import SessionLocal
from src.models.niche import Niche

NICHES = [
    {
        "name": "fitness",
        "keywords": ["workout", "gym", "fitness", "exercise", "training"],
        "hashtag_seeds": ["gymtok", "fitness", "workout", "fittok", "gym"],
        "is_active": True,
    },
    {
        "name": "cooking",
        "keywords": ["recipe", "food", "cooking", "meal", "kitchen"],
        "hashtag_seeds": ["foodtok", "cooking", "recipe", "easyrecipes", "mealprep"],
        "is_active": True,
    },
    {
        "name": "tech",
        "keywords": ["technology", "ai", "coding", "software", "gadget"],
        "hashtag_seeds": ["techtok", "ai", "coding", "programming", "tech"],
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
