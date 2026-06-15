"""
Fill the day-7 view count on a recorded post (P3.5 Task 3).

WHY THIS EXISTS:
  Views climb forever, so the label is pinned to ONE reading ~7 days after posting (TikTok's
  algorithm has mostly resolved a video's reach by then). This CLI is run once per post at that
  day-7 mark to record the snapshot.

THE SEAM (the point of this file):
  The count comes from get_view_count(args) — a single function whose v1 body just returns the
  number passed on the CLI (manual entry). LATER, to automate, swap ONLY this function's body to
  call the apidojo scraper or the TikTok Display API; nothing else in the loop changes. It is a
  function boundary, deliberately NOT a class hierarchy (YAGNI until a second source exists).

USAGE:
  uv run python scripts/enter_views.py --id 12 --views 842 --likes 30 --comments 5 --shares 2
  uv run python scripts/enter_views.py --url https://www.tiktok.com/@me/video/456 --views 842

DESIGN:
  enter_views(session, ...) takes a session passed in (testable against in-memory SQLite); the
  argparse wrapper (main) opens the real Postgres SessionLocal. Same logic/CLI split as record_post.py.
"""

import argparse
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models.published_video import PublishedVideo


def get_view_count(views: int) -> int:
    """
    Return the day-7 view count for a post.

    v1 = MANUAL: returns the number the user passed on the CLI. This is the swap seam — to
    automate, replace this body with an apidojo scrape or a TikTok Display API call that fetches
    the count for the post, keyed off something on the row (e.g. tiktok_url / post_id). The
    callers and the rest of the loop are unchanged by that swap.
    """
    return views


def _resolve_post(session: Session, post_id: int | None, url: str | None) -> PublishedVideo:
    """Fetch the target PublishedVideo by id or url; raise if not found / under-specified."""
    if post_id is not None:
        pv = session.get(PublishedVideo, post_id)
    elif url is not None:
        pv = session.query(PublishedVideo).filter_by(tiktok_url=url).one_or_none()
    else:
        raise ValueError("Provide either --id or --url to identify the post.")
    if pv is None:
        raise ValueError(f"No published_video found for id={post_id!r} / url={url!r}.")
    return pv


def enter_views(
    session: Session,
    post_id: int | None = None,
    url: str | None = None,
    views: int = 0,
    likes: int | None = None,
    comments: int | None = None,
    shares: int | None = None,
) -> PublishedVideo:
    """
    Set the day-7 counts on one post and stamp fetched_at.

    Identifies the row by post_id or url. Pulls the view count through get_view_count (the seam),
    sets the optional like/comment/share counts as given, sets fetched_at = now (UTC), commits.
    Returns the updated row.
    """
    pv = _resolve_post(session, post_id, url)
    pv.view_7d = get_view_count(views)
    if likes is not None:
        pv.like_7d = likes
    if comments is not None:
        pv.comment_7d = comments
    if shares is not None:
        pv.share_7d = shares
    pv.fetched_at = datetime.now(timezone.utc)
    session.commit()
    return pv


def main() -> None:
    """Parse CLI args, open a real Postgres session, fill the day-7 counts, print the result."""
    parser = argparse.ArgumentParser(description="Enter the day-7 view count for a posted video.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=int, help="published_videos row id.")
    group.add_argument("--url", help="TikTok post URL.")
    parser.add_argument("--views", type=int, required=True, help="Day-7 view count.")
    parser.add_argument("--likes", type=int, default=None, help="Day-7 like count (optional).")
    parser.add_argument("--comments", type=int, default=None, help="Day-7 comment count (optional).")
    parser.add_argument("--shares", type=int, default=None, help="Day-7 share count (optional).")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        pv = enter_views(
            session,
            post_id=args.id,
            url=args.url,
            views=args.views,
            likes=args.likes,
            comments=args.comments,
            shares=args.shares,
        )
        print(f"Updated published_video id={pv.id}: view_7d={pv.view_7d}, fetched_at={pv.fetched_at}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
