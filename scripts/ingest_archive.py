"""
One-off data-prep: ingest the local TikTok archive manifest into raw_content_items.

WHY THIS EXISTS:
  ~72K TikTok videos were scraped to D:\\tiktok_archive (full mp4 + thumb + subs + metadata),
  but only ~627 ever landed in the database. The premise generator and the mechanic miner
  both want the FULL winner pool — especially the ~22K videos with >=1M views, which the DB
  is almost entirely missing. This script copies the manifest's METADATA (views, likes,
  hashtags, author, etc.) into raw_content_items. It does NOT call any LLM and does NOT
  extract Blueprints — it is pure, free metadata ingest. Blueprint extraction (mechanics)
  is a separate, paid, deferred step.

WHAT IT READS:
  D:\\tiktok_archive\\manifest.jsonl — one JSON object per line, keys:
    id, niche, hashtags, path, video, subs, thumb, views, likes, comments, shares,
    bookmarks, author, scraped_at

FIELD MAPPING (manifest -> RawContentItem):
    id        -> platform_content_id   (platform fixed to "tiktok")
    niche     -> niche_id              (resolved via get-or-create on the niches table)
    hashtags  -> hashtags
    views/likes/comments/shares -> same
    bookmarks -> collect_count         (bookmarks == saves; collect_count is the existing column)
    author    -> author_username
    scraped_at-> collected_at
  url is synthesized from the video id (https://www.tiktok.com/@<author>/video/<id>).
  input_source is stamped "archive_ingest" so these rows are distinguishable from live scrapes.
  Fields the manifest does not carry (description/title/transcript/music/etc.) are left null —
  the manifest is metadata-only; richer fields would require re-scraping.

IDEMPOTENCY:
  raw_content_items has a unique constraint on (platform, platform_content_id). This script
  SKIPS any id already present (it does not overwrite — a prior full scrape may hold richer
  data than the manifest). Safe to re-run; safe to resume after interruption.

NICHE HANDLING:
  The archive spans 12 niches; the DB seeds only 4. Missing niches are created on the fly
  (get-or-create, name only + empty keyword/seed lists). The 8 created here:
  ai_asmr, ai_cinematic, futuristic_pov, historical_pov, liminal_weirdcore, real_cinematic,
  real_satisfying, satisfying_ai.

USAGE:
  uv run python -m scripts.ingest_archive                          # full ingest (~72K rows)
  uv run python -m scripts.ingest_archive --limit 200              # smoke a small slice first
  uv run python -m scripts.ingest_archive --manifest D:\\tiktok_archive\\manifest.jsonl

DESIGN:
  The DB work lives in ingest(session, manifest_path, limit) which takes a session passed in
  (caller owns its lifecycle) — same testable-seam pattern as the other scripts. The argparse
  wrapper (main) is the only part that opens a real SessionLocal. ingest() commits in batches
  so a long run is durable and a crash loses at most one batch.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load secrets BEFORE importing src.database (it reads DATABASE_URL at import).
load_dotenv("config/.env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.database import SessionLocal  # noqa: E402
from src.models.niche import Niche  # noqa: E402
from src.models.trend import RawContentItem  # noqa: E402

DEFAULT_MANIFEST = Path(r"D:\tiktok_archive\manifest.jsonl")
PLATFORM = "tiktok"
INPUT_SOURCE = "archive_ingest"
BATCH_SIZE = 1000


def _get_or_create_niche(session: Session, name: str, cache: dict[str, int]) -> int:
    """Resolve a niche name to its id, creating the niche if it does not exist.

    Caches name -> id in `cache` to avoid a query per row. Newly created niches get
    empty keyword / hashtag-seed lists and is_active defaulting to True (per the model).
    Flushes (not commits) so the new id is available immediately within the batch.
    """
    if name in cache:
        return cache[name]

    existing = session.execute(
        select(Niche).where(Niche.name == name)
    ).scalar_one_or_none()

    if existing is None:
        existing = Niche(name=name, keywords=[], hashtag_seeds=[])
        session.add(existing)
        session.flush()  # assigns existing.id without committing the whole batch

    cache[name] = existing.id
    return existing.id


def _parse_scraped_at(value: str | None) -> datetime:
    """Parse the manifest's ISO scraped_at into an aware datetime, defaulting to now (UTC).

    The manifest stores e.g. "2026-05-31T06:19:41.935958+00:00". datetime.fromisoformat
    handles that directly on 3.13. Falls back to now(UTC) if the field is missing or unparseable.
    """
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)


def ingest(session: Session, manifest_path: Path, limit: int | None = None) -> dict[str, int]:
    """Stream the manifest and upsert RawContentItem rows; return run counts.

    session: an open SQLAlchemy session (caller owns its lifecycle).
    manifest_path: path to manifest.jsonl (one JSON object per line).
    limit: if set, stop after processing this many manifest lines (for smoke runs).

    Returns a dict with keys: 'read', 'inserted', 'skipped', 'niches_created'.

    Idempotent: any (platform, platform_content_id) already present is skipped, not updated.
    Commits every BATCH_SIZE inserts so a long run is durable and resumable.
    """
    niche_cache: dict[str, int] = {}
    niches_before = session.execute(select(Niche)).scalars().all()
    initial_niche_names = {n.name for n in niches_before}

    read = inserted = skipped = 0

    with manifest_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if limit is not None and read >= limit:
                break
            line = line.strip()
            if not line:
                continue
            read += 1

            item = json.loads(line)
            content_id = str(item["id"])

            # Skip if this video is already in the table (don't clobber richer prior scrapes).
            exists = session.execute(
                select(RawContentItem.id).where(
                    RawContentItem.platform == PLATFORM,
                    RawContentItem.platform_content_id == content_id,
                )
            ).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue

            niche_id = _get_or_create_niche(session, item["niche"], niche_cache)
            author = item.get("author")

            row = RawContentItem(
                niche_id=niche_id,
                platform=PLATFORM,
                platform_content_id=content_id,
                url=f"https://www.tiktok.com/@{author or 'unknown'}/video/{content_id}",
                views=int(item.get("views") or 0),
                likes=int(item.get("likes") or 0),
                comments=int(item.get("comments") or 0),
                shares=int(item.get("shares") or 0),
                collect_count=int(item.get("bookmarks") or 0),
                hashtags=item.get("hashtags") or [],
                author_username=author,
                input_source=INPUT_SOURCE,
                collected_at=_parse_scraped_at(item.get("scraped_at")),
            )
            session.add(row)
            inserted += 1

            if inserted % BATCH_SIZE == 0:
                session.commit()

    session.commit()

    niches_after = session.execute(select(Niche)).scalars().all()
    niches_created = len({n.name for n in niches_after} - initial_niche_names)

    return {
        "read": read,
        "inserted": inserted,
        "skipped": skipped,
        "niches_created": niches_created,
    }


def main() -> None:
    """CLI wrapper: open a real SessionLocal, run ingest, print the run counts."""
    parser = argparse.ArgumentParser(
        description="Ingest the local TikTok archive manifest into raw_content_items (metadata only, no LLM)."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Path to manifest.jsonl (default: {DEFAULT_MANIFEST}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most this many manifest lines (for a smoke run). Default: all.",
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        raise SystemExit(f"Manifest not found: {args.manifest}")

    session = SessionLocal()
    try:
        counts = ingest(session, args.manifest, limit=args.limit)
    finally:
        session.close()

    print(
        f"Done. read={counts['read']} inserted={counts['inserted']} "
        f"skipped={counts['skipped']} niches_created={counts['niches_created']}"
    )


if __name__ == "__main__":
    main()
