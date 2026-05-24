"""
Instagram Reels scraper backed by an Apify actor.

Apify exposes IG data through async actor runs; this module starts a run,
polls for completion within a hard time budget, and normalizes the
inconsistent field names the actor returns across versions.
"""

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from src.models.trend import RawContentItem
from src.scrapers.base import BaseScraper


class InstagramScraper(BaseScraper):
    """
    Apify-backed Instagram Reels scraper.

    Polling cap = poll_interval_seconds * poll_attempts, additionally
    hard-capped by max_duration_seconds.
    """

    platform = "instagram"
    base_url = "https://api.apify.com/v2"  
    _hashtag_re = re.compile(r"(?<!\w)#(\w+)")
  

    def __init__(self, db, actor_id: str = "apify~instagram-reel-scraper", poll_interval_seconds: float=5.0, poll_attempts: int=24, max_duration_seconds: int=90):
        """Poll budget = poll_interval_seconds * poll_attempts, capped by max_duration_seconds."""
        super().__init__(db)
        self.api_token = os.getenv("APIFY_API_TOKEN")
        self.actor_id = actor_id
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_attempts = poll_attempts
        self.max_duration_seconds = max_duration_seconds


    async def fetch_trending(self, max_results = 20, niche_id = None, query = None) -> list[RawContentItem]:
        """Fetch recent Instagram Reels for a username or profile URL.

        Args:
            max_results: capped internally at 50 (actor limit).
            niche_id: FK attached to each saved item.
            query: username or profile URL; defaults to "instagram" if omitted.

        Returns:
            List of saved RawContentItems (deduped via BaseScraper.save_items).
        """
        if not self.api_token:
            raise RuntimeError("APIFY_API_TOKEN is not set")
        
        # Actor requires a username or profile URL — default to a high-volume public account
        target = query if query else "instagram"

        run_input = {
            "username": [target],
            "resultsLimit": max(1, min(max_results, 50)),
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",

        }

        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            run = await self._start_run(client, headers, run_input)
            run_id = run["id"]

            finished_run =await self._poll_run(client, headers, run_id)
            dataset_id = finished_run.get("defaultDatasetId")
            if not dataset_id:
                return []
            
            dataset_items = await self._fetch_dataset_items(client, headers, dataset_id)
        
        items = []
        for item in dataset_items:
            normalized = self._normalize_item(item, niche_id)
            if normalized is not None:
                items.append(normalized)

        return self.save_items(items)

    async def _start_run(self, client: httpx.AsyncClient, headers: dict[str, str], run_input: dict[str, Any]):
        """POST to Apify to start an actor run; return the run metadata dict."""
        response = await client.post(
            f"/acts/{self.actor_id}/runs",
            headers=headers,
            json=run_input,
            params={"token": self.api_token},
        )
        response.raise_for_status()
        data = response.json()
        return data["data"]
    
    async def _poll_run(self, client: httpx.AsyncClient, headers: dict[str, str], run_id: str):
        """Poll run status until SUCCEEDED or terminal failure; raise TimeoutError if budget exceeded."""
        started = time.monotonic()

        for _ in range(self.poll_attempts):
            if time.monotonic() - started > self.max_duration_seconds:
                raise TimeoutError(
                    f"Instagram Apify run exceeded {self.max_duration_seconds} seconds"
                )

            response = await client.get(
                f"/actor-runs/{run_id}",
                headers=headers,
                params={"token": self.api_token},
            )

            response.raise_for_status()
            data = response.json()["data"]

            status = data.get("status")
            
            if status == "SUCCEEDED":
                return data 
            if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
                raise RuntimeError(f"Instagram Apify run ended with status {status}")
        
            await asyncio.sleep(self.poll_interval_seconds)

        raise TimeoutError(f"Instagram Apify run did not finish after {self.poll_attempts} polls")


    async def _fetch_dataset_items(self, client: httpx.AsyncClient, headers: dict[str, str], dataset_id: str):
        """Fetch all items from a completed Apify dataset; return empty list on non-list response."""
        response = await client.get(
            f"/datasets/{dataset_id}/items",
            headers=headers,
            params={"token": self.api_token,
                "clean": "true",
            }
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    
    
    def _normalize_item(self, item, niche_id):
        # Apify Instagram actors return the post identifier under different keys
        # depending on actor version and post type (reel vs. post). Try in priority order.
        content_id = self._pick_first_str(item, ["id", "shortCode", "code", "postId"])
        if not content_id:
            return None

        caption = self._pick_first_str(item, ["caption", "title", "text"])

        url = self._pick_first_str(item, ["url", "postUrl"]) or f"https://www.instagram.com/reel/{content_id}/"

        views = self._to_int(self._pick_first(item, ["videoViewCount", "videoPlayCount", "playCount", "viewCount"]))

        likes = self._to_int(self._pick_first(item, ["likesCount", "likes", "likeCount"]))

        comments = self._to_int(self._pick_first(item, ["commentsCount", "comments", "commentCount"]))

        shares = self._to_int(self._pick_first(item, ["sharesCount", "shares", "shareCount"]))

        audio_id = self._pick_first_str(item,["audioId", "musicCanonicalId", "audioName"])

        duration = self._to_int(self._pick_first(item, ["videoDuration", "duration", "videoDurationSeconds"]))

        published_at = self._parse_datetime(self._pick_first(item, ["timestamp", "takenAtTimestamp", "createdAt"]))

        hashtags = self._extract_hashtags(
            caption,
            self._pick_first(item, ["hashtags", "hashTags", "tags"]),
        )

        return RawContentItem(
            niche_id=niche_id,
            platform=self.platform,
            platform_content_id=content_id,
            url=url,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            audio_id=audio_id,
            hashtags=hashtags,
            duration_in_seconds=duration if duration > 0 else None,
            content_format="reel",
            published_at=published_at,
        )

    def _extract_hashtags(self, caption, api_hashtags) -> list[str]:
        """Merge hashtags from caption text and API hashtag list into a sorted deduplicated list."""
        out: set[str] = set()
        if caption:
            out.update(h.lower() for h in self._hashtag_re.findall(caption))
        if isinstance(api_hashtags, list):
            for tag in api_hashtags:
                if isinstance(tag, str) and tag.strip():
                    out.add(tag.strip().lower().lstrip("#"))
        return sorted(out)

    def _pick_first(self, item: dict, keys):
        """Return first non-None value from item for the given keys, or None if none found."""
        for key in keys:
            if key in item and item[key] is not None:
                return item[key]
        return None
    
    def _pick_first_str(self, item, keys):
        """Return first non-None value as a non-empty string, or None if all keys missing/empty."""
        value = self._pick_first(item, keys)
        if value is None:
            return None
        if isinstance(value, str) and value.strip():
            return value
        return str(value)

    def _to_int(self, value: Any) -> int:
        """Safely cast to int; return 0 on TypeError/ValueError."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _parse_datetime(self, value):
        """Parse Unix epoch (int/float) or ISO 8601 string into a UTC-aware datetime; return None on failure."""
        # Actor returns either Unix epoch (int|float) or ISO 8601 string.
        # Coerce both into UTC-aware datetime; storage column is timezone-aware.
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                return None

        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return None

        return None