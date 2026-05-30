"""
Archive writer: turn one raw Apify item into on-disk files + a manifest record.

Writes metadata.json (the full raw payload — the cheap, always-present index),
then downloads the three media files (video critical, subtitle + thumbnail
optional). The video download is the make-or-break: its bytes are what the
expiring signed URL would otherwise lose, so a video failure makes the whole
item a failure even though metadata.json is still written for audit.
"""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.archive import paths

# Downloader signature: (url, target_path, timeout) -> success bool.
Downloader = Callable[..., bool]


def _english_subtitle_url(raw: dict[str, Any]) -> str | None:
    """Return the first English subtitle URL, or None."""
    subs = raw.get("subtitleInformation") or []
    if not isinstance(subs, list):
        return None
    for sub in subs:
        if not isinstance(sub, dict):
            continue
        if str(sub.get("language_code") or "").lower().startswith("en"):
            return sub.get("url")
    return None


def _int(value: Any) -> int:
    """Coerce a metric to int, defaulting to 0."""
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def archive_item(
    root: Path,
    raw: dict[str, Any],
    niche: str,
    downloader: Downloader,
) -> tuple[bool, dict[str, Any]]:
    """
    Archive one raw item to disk and build its manifest/failure record.

    Always writes metadata.json. Downloads video (critical), subtitle and
    thumbnail (optional). Returns (success, record) where success is False iff
    the critical video download failed. The record carries per-file booleans
    plus the fields needed to query the manifest later.

    Args:
        root: archive root.
        raw: raw Apify item dict.
        niche: niche label for this scrape target.
        downloader: callable(url, target_path, timeout) -> bool.

    Returns:
        (success, record). On failure, record additionally carries ``stage``
        and ``error`` so it can be written to failures.jsonl.
    """
    video_id = str(raw["id"])
    d = paths.item_dir(root, video_id)
    d.mkdir(parents=True, exist_ok=True)

    # metadata.json — always written, the index even when media fails.
    (d / paths.METADATA_NAME).write_text(
        json.dumps(raw, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    video_url = (raw.get("video") or {}).get("url")
    thumb_url = (raw.get("video") or {}).get("cover")
    sub_url = _english_subtitle_url(raw)

    video_ok = bool(video_url) and downloader(video_url, d / paths.VIDEO_NAME)
    subs_ok = bool(sub_url) and downloader(sub_url, d / paths.SUBS_NAME)
    thumb_ok = bool(thumb_url) and downloader(thumb_url, d / paths.THUMB_NAME)

    channel = raw.get("channel") or {}
    record: dict[str, Any] = {
        "id": video_id,
        "niche": niche,
        "hashtags": raw.get("hashtags") or [],
        "path": f"{paths.shard_for(video_id)}/{video_id}",
        "video": bool(video_ok),
        "subs": bool(subs_ok),
        "thumb": bool(thumb_ok),
        "views": _int(raw.get("views")),
        "likes": _int(raw.get("likes")),
        "comments": _int(raw.get("comments")),
        "shares": _int(raw.get("shares")),
        "bookmarks": _int(raw.get("bookmarks")),
        "author": channel.get("username"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    if not video_ok:
        record["stage"] = "video_download"
        record["error"] = "no_video_url" if not video_url else "download_failed"
        record["url"] = video_url
        return False, record

    return True, record
