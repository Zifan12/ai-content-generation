"""
Fetch and persist TikTok transcripts from Apify-sourced WebVTT subtitles.

TikTok's CDN-hosted subtitle files repeat caption segments and ship with cue
timestamps; this module strips both so downstream consumers (Blueprint
extractor, RAG indexer) get clean plain text.
"""

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session


from src.models.transcript import Transcript
from src.models.trend import RawContentItem
from src.observability.tracing import traced

logger = logging.getLogger(__name__)

class TranscriptFetcher:
    """
    Fetches and persists transcripts for TikTok RawContentItems.

    Uses Apify-sourced subtitle_url (WebVTT/SRT) as the transcript source.
    Deduplicates by content_item_id before fetching.
    """


    def __init__(self, db: Session):
        self.db = db

    @traced(name="transcripts.fetch_one")
    def fetch_one(self, item: RawContentItem) -> Transcript | None:
        """
        Fetch and persist transcript for a single RawContentItem.

        Returns existing Transcript if already stored. Returns None if
        subtitle_url is missing or the fetch/parse fails.
        """
        existing = self.db.scalar(
            select(Transcript).where(Transcript.content_item_id == item.id)
        )
        if existing:
            return existing

        if item.subtitle_url is None:
            logger.warning("Item %s has no subtitle_url; skipping transcript", item.id)
            return None
        
        text = self._fetch_from_subtitles(item.subtitle_url)
        if text is None:
            return None
        
        transcript = Transcript(
            content_item_id=item.id, 
            text=text, 
            source="apify_subtitles"
        )

        self.db.add(transcript)
        self.db.commit()
        return transcript

        

    def _fetch_from_subtitles(self, subtitle_url: str) -> str | None:
        """
        Download and parse a WebVTT subtitle file into plain text.

        Strips WEBVTT header, timestamp lines, blank lines, and consecutive
        duplicate caption segments (TikTok CDN often repeats segments).
        Returns None on HTTP error or if parsed text is empty.
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(subtitle_url)
                resp.raise_for_status()
                text = resp.text

            lines = text.splitlines()
            kept = []
            prev = None

            for line in lines:
                line = line.strip()
                # WebVTT: skip global header token and cue timestamp lines
                if not line or line == "WEBVTT" or "-->" in line:
                    continue

                if line != prev:
                    kept.append(line)
                prev = line
            result=" ".join(kept)
            return result if result else None
        
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error fetching subtitles: {subtitle_url} - {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error processing subtitles: {subtitle_url}")
            return None


        