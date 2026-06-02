"""
One-shot script: sample BlueprintRecords from Postgres and write them as
BlueprintCandidate JSONL to data/golden/generation_targets.jsonl.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .venv\\Scripts\\python.exe -m scripts.build_generation_targets

Idempotent — overwrites the file each run.
"""

import json
import random
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config/.env")

from sqlalchemy import select
from src.database import SessionLocal
from src.models.blueprint import BlueprintRecord

TIER1_FIELDS = [
    "hook_type", "share_hook_type", "comment_bait_type",
    "pacing", "loop_type", "audio_type",
    "visual_complexity", "color_mood",
    "primary_emotion", "duration_band",
]

EXTRACTOR_VERSION = "v3.1"
N = 20
SEED = 42
OUT = Path("data/golden/generation_targets.jsonl")


def main():
    db = SessionLocal()
    try:
        records = db.execute(
            select(BlueprintRecord).where(
                BlueprintRecord.extractor_version == EXTRACTOR_VERSION
            )
        ).scalars().all()

        print(f"Found {len(records)} v3.1 blueprints")

        random.seed(SEED)
        sampled = random.sample(records, min(N, len(records)))

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            for i, record in enumerate(sampled, 1):
                blueprint_template = {
                    k: record.blueprint_data.get(k)
                    for k in TIER1_FIELDS
                    if record.blueprint_data.get(k) is not None
                }
                candidate = {
                    "rank": i,
                    "niche_label": record.blueprint_data.get("niche_label", "surreal_hyperreal"),
                    "blueprint_template": blueprint_template,
                    "evidence": {
                        "matching_items": 1,
                        "median_views": 0,
                        "p90_views": 0,
                        "trend_slope_4wk_pct": 0.0,
                        "rationale": f"sampled from blueprint {record.content_item_id}",
                    },
                }
                f.write(json.dumps(candidate) + "\n")

        print(f"Wrote {len(sampled)} targets to {OUT}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
