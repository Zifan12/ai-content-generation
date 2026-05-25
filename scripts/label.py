"""
Golden set labeling tool — creates ground truth for eval gates.

PIPELINE ROLE:
  Scrape (apidojo) → LABEL (this file) → Extract Blueprints → Eval gates → Generation

WHY THIS FILE EXISTS:
  This is the human-in-the-loop ground truth source. All downstream eval gates
  (P1 harness, P4 ML predictor training) depend on labels created here. Without
  this, we cannot measure if extractors/generators actually work.

WHAT IT DOES:
  1. Loads unlabeled RawContentItems from DB (random sample to reduce bias)
  2. Shows video stats + auto-suggested virality class to annotator (stdout)
  3. Collects manual label: v/m/f/s (viral/mid/flop/suspicious) + optional hook text
  4. Saves to dual destinations:
     - JSONL: append-only audit log (immutable, auditable)
     - DB (GoldenLabel table): queryable by eval harness

HOW SCORING WORKS:
  Imports weighted_er() + classify() from src.analysis.rubric — the single
  source of truth for the labeling rubric. Both this script and the
  RuleBasedScorer in src/analysis/scorer.py consume the same module so
  ground-truth labels and eval-harness baseline scores cannot drift.

RUNNING:
  uv run python scripts/label.py
  Follow prompts; type v/m/f/s + Enter. Optional: add hook text + notes.
"""

import sys
import json
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv("config/.env")

from sqlalchemy import func, select                  # noqa: E402
from src.database import SessionLocal                # noqa: E402
from src.models.eval import GoldenLabel              # noqa: E402
from src.models.trend import RawContentItem          # noqa: E402
from src.models.niche import Niche                   # noqa: E402
from src.analysis.rubric import classify, weighted_er  # noqa: E402

VALID_CLASSES = {"v": "viral", "m": "mid", "f": "flop", "s": "suspicious"}

def show_video(item: RawContentItem, er: float, suggestion: str, reason: str, index: int, db) -> None:
    """
    Display video stats and auto-suggestion to stdout for manual labeling.
    
    Args:
        item: RawContentItem to display.
        er: Weighted engagement rate (%).
        suggestion: Auto-suggested virality class.
        reason: Explanation string for the suggestion.
        index: Video number in current labeling session.
        db: SQLAlchemy session for niche lookup.
    """
    niche = db.execute(select(Niche).where(Niche.id == item.niche_id)).scalar_one_or_none()
    niche_name = niche.name if niche else str(item.niche_id)
    print(f"\n--- Video {index} ---")
    print(f"URL      : {item.url}")
    print(f"Views    : {item.views:,}")
    print(f"Likes    : {item.likes:,}")
    print(f"Comments : {item.comments:,}")
    print(f"Shares   : {item.shares:,}")
    print(f"Weighted ER: {er:.2f}%")
    print(f"Hashtags : {' '.join('#' + h for h in item.hashtags)}")
    print(f"Niche ID : {niche_name}")
    print(f"\nAuto-suggest: {suggestion.upper()}  ({reason})")

def load_unlabeled_items(db, limit: int = 100) -> list[RawContentItem]:
    """
    Load a random sample of unlabeled RawContentItems for annotation.
    
    Uses an outer join (NOT IN subquery) to exclude items already in GoldenLabel.
    Results are randomized to reduce annotator bias and ensure diverse coverage.
    
    Args:
        db: SQLAlchemy session.
        limit: Maximum number of items to return (default 100).
    
    Returns:
        List of RawContentItems not yet labeled, randomly ordered.
    """
    already_labeled = select(GoldenLabel.content_item_id).scalar_subquery()
    stmt = (
        select(RawContentItem)
        .where(~RawContentItem.id.in_(already_labeled))
        .order_by(func.random())
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()

def save_label(db, jsonl_path: Path, item: RawContentItem, virality_class: str, hook_text: str | None, notes: str | None) -> None:
    """
    Save a label to both JSONL (audit log) and DB (GoldenLabel table).
    
    Dual write ensures auditability (JSONL log) and queryability (DB).
    All engagement stats are recalculated and stored with the label for
    reproducibility (labels should not depend on stale data).
    
    Args:
        db: SQLAlchemy session.
        jsonl_path: Path to append-only JSONL log file.
        item: RawContentItem being labeled.
        virality_class: One of "viral", "mid", "flop", "suspicious".
        hook_text: (Optional) Best hook text extracted from video.
        notes: (Optional) Annotator notes.
    """
    record = {
        "id": item.id,
        "platform_content_id": item.platform_content_id,
        "url": item.url,
        "views": item.views,
        "likes": item.likes,
        "comments": item.comments,
        "shares": item.shares,
        "weighted_er": round(weighted_er(item.views, item.likes, item.comments, item.shares), 4),
        "virality_class": virality_class,
        "best_hook_text": hook_text,
        "annotator": "zifan",
        "notes": notes,
    }
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    label = GoldenLabel(
        content_item_id=item.id,
        virality_class=virality_class,
        best_hook_text=hook_text,
        annotator="zifan",
        notes=notes
    )
    db.add(label)
    db.commit()


def main():
    jsonl_path = Path("data/golden/labels.jsonl")
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()

    try:
        total_labeled = db.execute(select(func.count()).select_from(GoldenLabel)).scalar_one()
        print(f"\n[{total_labeled} already labeled — 100 target]\n")
        items = load_unlabeled_items(db)
        if not items:
            print("All 100 target labels complete (or no unlabeled items remain).")
            return
        for i, item in enumerate(items, start=total_labeled+1):
            er = weighted_er(item.views, item.likes, item.comments, item.shares)
            suggestion, reason = classify(item.views, er)
            show_video(item, er, suggestion, reason, i, db)
            while True:
                raw = input("Label [v/m/f/s/skip/q]: ").strip().lower()
                if raw == "q":
                    print("Quit."); return 
                elif raw == "skip":
                    print("Skipped.\n"); break
                if raw in VALID_CLASSES:
                    valid_class = VALID_CLASSES[raw]
                    hook = input("Hook text (Enter to skip): ").strip() or None
                    notes = input("Notes (Enter to skip): ").strip() or None
                    save_label(db, jsonl_path, item, valid_class, hook, notes)
                    print(f"Saved. ({i} labeled so far)\n")
                    break
                print("  Invalid. Use v/m/f/s/skip/q.")
    finally:
        db.close()

if __name__ == "__main__":
    main()