"""
YouTube search + transcript enrichment for the reference harvester.

Mirrors two existing patterns rather than inventing new ones:
- yt-dlp usage: metadata-first, Python-API-only (OpenMontage
  ``video_downloader.py`` — never subprocess, an audit C1 lesson).
- WebVTT transcript parsing: strip header/timestamp/blank lines and collapse
  consecutive-duplicate caption segments (``src/enrichment/transcripts.py``).
"""

import logging

import httpx
import yt_dlp  # type: ignore[import-untyped]

from src.reference.schemas import VideoCandidate

logger = logging.getLogger(__name__)

_TRANSCRIPT_MAX_CHARS = 1500


def search_youtube(query: str, limit: int) -> list[VideoCandidate]:
    """
    Flat yt-dlp search (``ytsearchN:``) — no download, no per-video metadata
    fetch. Fields unavailable in flat mode (description, transcript) are left
    at their defaults and filled in later by ``enrich_candidate`` for the
    shortlisted subset only, keeping the search cheap.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    entries = (info or {}).get("entries") or []
    candidates = []
    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id", "")
        candidates.append(
            VideoCandidate(
                video_id=video_id,
                url=entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                title=entry.get("title", ""),
                channel=entry.get("channel") or entry.get("uploader") or "",
                duration_seconds=float(entry.get("duration") or 0.0),
                view_count=entry.get("view_count"),
                description="",
                transcript_excerpt=None,
            )
        )
    return candidates


def enrich_candidate(candidate: VideoCandidate) -> VideoCandidate:
    """
    Full metadata fetch (description) + subtitle/auto-caption fetch for one
    shortlisted candidate. Returns a NEW ``VideoCandidate`` instance — the
    input is never mutated.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(candidate.url, download=False) or {}

    return candidate.model_copy(
        update={
            "description": info.get("description") or "",
            "transcript_excerpt": _fetch_transcript_excerpt(info),
        }
    )


def _fetch_transcript_excerpt(info: dict) -> str | None:
    """
    Pick the English subtitle track (real captions preferred over
    auto-generated), fetch its WebVTT body, and parse it into deduped plain
    text truncated to ``_TRANSCRIPT_MAX_CHARS``. Returns None when no English
    track exists, the fetch fails, or the parsed text is empty.
    """
    subs = info.get("subtitles") or {}
    auto_captions = info.get("automatic_captions") or {}
    track = subs.get("en") or auto_captions.get("en")
    if not track:
        return None

    vtt_url = next((fmt["url"] for fmt in track if fmt.get("ext") == "vtt"), None)
    if vtt_url is None:
        return None

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(vtt_url)
            resp.raise_for_status()
            text = resp.text
    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching subtitles: %s - %s", vtt_url, e)
        return None

    kept: list[str] = []
    prev = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line:
            continue
        if line != prev:
            kept.append(line)
        prev = line

    result = " ".join(kept)
    return result[:_TRANSCRIPT_MAX_CHARS] if result else None
