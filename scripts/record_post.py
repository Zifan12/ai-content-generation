"""
Record one manually-posted video into published_videos (P3.5 Task 2).

WHY THIS EXISTS:
  Posting is manual (hand-upload to TikTok + add a trending sound). This CLI is run right
  after that upload to log the post: which blueprint conditioned it, the live TikTok URL,
  and when it went up. View counts are NOT set here — they are filled later by enter_views.py
  at the day-7 mark.

USAGE:
  uv run python scripts/record_post.py --blueprint-id 123 --url https://www.tiktok.com/@me/video/456
  uv run python scripts/record_post.py --blueprint-id 123 --url <url> --posted-at 2026-06-15T14:30:00 --niche surreal_hyperreal
  uv run python scripts/record_post.py --url <url>  # non-blueprint pitch (e.g. Exilus) — blueprint_id left null

DESIGN:
  The DB work lives in record_post(session, ...) which takes a session passed in — so unit
  tests call it directly against an in-memory SQLite session with no subprocess. The argparse
  wrapper (main) is the only part that opens a real Postgres SessionLocal. This logic/CLI split
  is the testable-seam pattern reused by the other P3.5 CLIs.
"""

import argparse
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models.published_video import PublishedVideo


def record_post(
    session: Session,
    blueprint_id: int | None,
    tiktok_url: str,
    posted_at: datetime | None = None,
    niche: str = "surreal_hyperreal",
) -> PublishedVideo:
    """
    Insert one PublishedVideo row and return it (with its assigned id).

    session: an open SQLAlchemy session (caller owns its lifecycle).
    blueprint_id: FK to the BlueprintRecord that conditioned this video. None for videos
        not sourced from the blueprint-conditioned lane (e.g. Exilus/news-reactive pitches) —
        write_back_percentiles already no-ops on a null blueprint_id.
    tiktok_url: the live post URL.
    posted_at: when it was posted; defaults to now (UTC) if not given.
    niche: denormalized niche label for per-niche percentile grouping later.

    Counts (view_7d etc.) are intentionally left null — filled later by enter_views.py.
    Commits before returning so the row's id is populated.
    """
    pv = PublishedVideo(
        blueprint_id=blueprint_id,
        tiktok_url=tiktok_url,
        posted_at=posted_at or datetime.now(timezone.utc),
        niche=niche,
    )
    session.add(pv)
    session.commit()
    return pv


def main() -> None:
    """Parse CLI args, open a real Postgres session, record the post, print the new row id."""
    parser = argparse.ArgumentParser(description="Record a manually-posted TikTok video.")
    parser.add_argument("--blueprint-id", type=int, default=None, help="FK to the conditioning blueprint (omit for non-blueprint pitches, e.g. Exilus).")
    parser.add_argument("--url", required=True, help="Live TikTok post URL.")
    parser.add_argument(
        "--posted-at",
        default=None,
        help="ISO datetime the video was posted (e.g. 2026-06-15T14:30:00). Defaults to now (UTC).",
    )
    parser.add_argument("--niche", default="surreal_hyperreal", help="Niche label.")
    args = parser.parse_args()

    posted_at = datetime.fromisoformat(args.posted_at) if args.posted_at else None

    session = SessionLocal()
    try:
        pv = record_post(
            session,
            blueprint_id=args.blueprint_id,
            tiktok_url=args.url,
            posted_at=posted_at,
            niche=args.niche,
        )
        print(f"Recorded published_video id={pv.id} (blueprint_id={pv.blueprint_id}, posted_at={pv.posted_at})")
    finally:
        session.close()


if __name__ == "__main__":
    main()
