import sys
import json
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv("config/.env")

from sqlalchemy import func                          # noqa: E402
from src.database import SessionLocal                # noqa: E402
from src.models.eval import GoldenLabel              # noqa: E402
from src.models.trend import RawContentItem          # noqa: E402
from src.models.niche import Niche                   # noqa: E402

VALID_CLASSES = {"v": "viral", "m": "mid", "f": "flop", "s": "suspicious"}

def compute_weighted_er(views: int, likes: int, comments: int, shares: int) -> float:
    if views == 0:
        return 0.0 
    return (likes * 1 + comments * 2 + shares * 3) / views * 100


def auto_suggest_class(views: int, weighted_er: float) -> tuple[str, str]:
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
    niche = db.query(Niche).filter(Niche.id == item.niche_id).first()
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
    already_labeled = db.query(GoldenLabel.content_item_id).scalar_subquery()
    return (
        db.query(RawContentItem)
        .filter(~RawContentItem.id.in_(already_labeled))
        .order_by(func.random())
        .limit(limit)
        .all()
    )

def save_label(db, jsonl_path: Path, item: RawContentItem, virality_class: str, hook_text: str | None, notes: str | None) -> None:
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
        total_labeled = db.query(GoldenLabel).count()
        print(f"\n[{total_labeled} already labeled — 100 target]\n")
        items = load_unlabeled_items(db)
        if not items:
            print("All 100 target labels complete (or no unlabeled items remain).")
            return
        for i, item in enumerate(items, start=total_labeled+1):
            er = compute_weighted_er(item.views, item.likes, item.comments, item.shares)
            suggestion, reason = auto_suggest_class(item.views, er)
            show_video(item, er, suggestion, reason, i, db)
            # prompt loop
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