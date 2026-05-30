"""
Orchestrator + CLI for the Apify credit-burn archive.

Walks the seed list, runs one Apify scrape per hashtag, charges the budget on
items RETURNED (Apify's billing unit), and archives each new item to the HDD.
Idempotent via the manifest; stops cleanly when the local budget cap is hit;
prints a summary. The hard backstop is a separately-configured Apify console
spend cap — set that before any real run.

Usage:
  uv run python -m scripts.archive.run --dry-run
  uv run python -m scripts.archive.run                 # real burn, D:\\tiktok_archive
  uv run python -m scripts.archive.run --niche surreal_hyperreal --cap-usd 10
"""

import argparse
import json
import os
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from scripts.archive.apify_client import ApifyClient
from scripts.archive.budget import BudgetTracker
from scripts.archive.downloader import download
from scripts.archive.manifest import ManifestStore
from scripts.archive.seeds import Seed, load_seeds
from scripts.archive.writer import archive_item

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = Path(r"D:\tiktok_archive")
SEEDS_PATH = PROJECT_ROOT / "config" / "archive_seeds.yaml"


def run_archive(
    root: Path,
    seeds: list[Seed],
    client: Any,
    downloader: Callable[..., bool],
    max_items: int,
    cap_usd: float,
    location: str = "US",
    sort_type: str = "RELEVANCE",
) -> dict[str, Any]:
    """
    Execute the archive loop over seeds. Returns a summary dict.

    Charges the budget on items returned per run, skips ids already in the
    manifest, archives the rest, and records failures separately. Stops
    launching new runs once the budget is exhausted.

    Args:
        root: archive root path.
        seeds: list[Seed] to scrape.
        client: object with run_hashtag(hashtag, max_items, location, sort_type).
        downloader: callable(url, target, timeout) -> bool.
        max_items: per-run item cap.
        cap_usd: local budget cap.
        location, sort_type: passed through to the actor.

    Returns:
        Summary dict with archived/skipped/failed/items_returned/runs_executed/
        est_spend_usd/remaining_usd.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = ManifestStore(root)
    budget = BudgetTracker(root, cap_usd=cap_usd)

    archived = skipped = failed = runs_executed = 0

    for seed in seeds:
        if budget.exhausted():
            break
        items = client.run_hashtag(
            seed.hashtag, max_items=max_items, location=location, sort_type=sort_type
        )
        runs_executed += 1
        budget.charge(len(items))

        for raw in items:
            video_id = str(raw.get("id") or "")
            if not video_id:
                continue
            if manifest.has(video_id):
                skipped += 1
                continue
            ok, record = archive_item(root, raw, seed.niche, downloader)
            if ok:
                manifest.add_success(record)
                archived += 1
            else:
                manifest.add_failure(record)
                failed += 1

    summary = {
        "archived": archived,
        "skipped": skipped,
        "failed": failed,
        "runs_executed": runs_executed,
        "items_returned": budget.items_returned,
        "est_spend_usd": round(budget.est_spend_usd, 4),
        "remaining_usd": round(budget.remaining(), 4),
    }
    _write_seeds_snapshot(root, seeds)
    return summary


def _write_seeds_snapshot(root: Path, seeds: list[Seed]) -> None:
    """Record which seeds this run used, for audit."""
    snapshot = {
        "at": datetime.now(timezone.utc).isoformat(),
        "seeds": [{"niche": s.niche, "hashtag": s.hashtag} for s in seeds],
    }
    (root / "seeds.snapshot.json").write_text(
        json.dumps(snapshot, indent=2), encoding="utf-8"
    )


def main() -> None:
    """CLI entry point: parse args, build units, run the loop, print summary."""
    parser = argparse.ArgumentParser(description="Apify credit-burn TikTok archive.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--max-items", type=int, default=1000)
    parser.add_argument("--cap-usd", type=float, default=30.0)
    parser.add_argument("--location", type=str, default="US")
    parser.add_argument(
        "--sort-type",
        type=str,
        default="RELEVANCE",
        choices=["RELEVANCE", "MOST_LIKED", "DATE_POSTED"],
    )
    parser.add_argument("--niche", type=str, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tiny real scrape (5 items, first seed) into a temp dir, then report.",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / "config" / ".env")
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN is not set")

    seeds = load_seeds(SEEDS_PATH, niche=args.niche)
    if not seeds:
        raise RuntimeError("No seeds matched")

    client = ApifyClient(token=token)

    if args.dry_run:
        seeds = seeds[:1]
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_archive(
                root=Path(tmp),
                seeds=seeds,
                client=client,
                downloader=download,
                max_items=5,
                cap_usd=args.cap_usd,
                location=args.location,
                sort_type=args.sort_type,
            )
            print("DRY RUN summary:", json.dumps(summary, indent=2))
        return

    try:
        summary = run_archive(
            root=args.root,
            seeds=seeds,
            client=client,
            downloader=download,
            max_items=args.max_items,
            cap_usd=args.cap_usd,
            location=args.location,
            sort_type=args.sort_type,
        )
    except KeyboardInterrupt:
        print("Interrupted — manifest/budget persisted, re-run to resume.")
        return
    print("Archive summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
