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
  compute_weighted_er() implements the virality heuristic:
    weighted_ER = (likes*1 + comments*2 + shares*3) / views * 100
  
  auto_suggest_class() applies thresholds (views ≥ 500K → viral, etc.)
  These rules are the labeling rubric — they MUST be auditable and consistent.

STRATEGIC NOTE:
  The heuristics here (weighted_er thresholds) are replicated in src/analysis/scorer.py
  for deterministic baseline scoring in evals. Changes here must be reflected there
  to keep ground truth and eval baseline in sync.

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

VALID_CLASSES = {"v": "viral", "m": "mid", "f": "flop", "s": "suspicious"}

def compute_weighted_er(views: int, likes: int, comments: int, shares: int) -> float:
    """
    Compute weighted engagement rate (wER) as a percentage.
    
    Formula: (likes*1 + comments*2 + shares*3) / views * 100
    
    Rationale: Not all engagement is equal. Likes are easy; comments and shares
    require deliberate user action. Weighting by 2x and 3x respectively ensures
    videos with deep engagement (comments/shares) score higher than those with
    only passive likes, even if total engagement counts are similar.
    
    Args:
        views: Total video views.
        likes: Total likes.
        comments: Total comments.
        shares: Total shares.
    
    Returns:
        Weighted engagement rate as percentage (0.0 if views==0).
    """
    if views == 0:
        return 0.0
    return (likes * 1 + comments * 2 + shares * 3) / views * 100


def auto_suggest_class(views: int, weighted_er: float) -> tuple[str, str]:
    """
    Automatically suggest a virality class based on view count and weighted ER.
    
    Decision tree (checked in order):
    1. views ≥ 500K AND wER < 1%  → "suspicious" (likely bot-boosted or gamed)
    2. views ≥ 500K AND wER ≥ 4%  → "viral" (high reach + strong engagement)
    3. views ≥ 500K AND 1.5% ≤ wER < 4%  → "mid" (high reach, moderate engagement)
    4. 50K ≤ views < 500K AND wER ≥ 1.5%  → "mid" (organic reach, good engagement)
    5. else  → "flop" (low reach or poor engagement)
    
    The thresholds balance reach (views) against engagement quality (wER).
    High views with low engagement triggers "suspicious" (potential fraud).
    
    Args:
        views: Total video views.
        weighted_er: Weighted engagement rate as percentage.
    
    Returns:
        Tuple of (virality_class, reason_string). Class is one of:
        "viral", "mid", "flop", "suspicious".
    """
    # High views + low engagement = likely bot-boosted; flag for manual review.
    if views >= 500_000 and weighted_er < 1.0:
        return "suspicious", f"views≥500K but wER={weighted_er:.2f}%<1%"
    if views >= 500_000 and weighted_er >= 4.0:
        return "viral", f"views≥500K, wER={weighted_er:.2f}%≥4%"
    if views >= 500_000 and weighted_er >= 1.5:
        return "mid", f"views≥500K, 1.5%≤wER={weighted_er:.2f}%<4%"
    if views >= 50_000 and weighted_er >= 1.5:
        return "mid", f"50K≤views<500K, wER={weighted_er:.2f}%≥1.5%"
    return "flop", f"views={views:,}<50K or wER={weighted_er:.2f}%<1.5%"

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
        "weighted_er": round(compute_weighted_er(item.views, item.likes, item.comments, item.shares), 4),
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
            er = compute_weighted_er(item.views, item.likes, item.comments, item.shares)
            suggestion, reason = auto_suggest_class(item.views, er)
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