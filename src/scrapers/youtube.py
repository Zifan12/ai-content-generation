import os
import re
from datetime import datetime
from typing import Any

import httpx

from src.models.trend import RawContentItem
from src.scrapers.base import BaseScraper


class YoutubeScraper(BaseScraper):
    """Scrapes YouTube Shorts via the YouTube Data API v3.

    Uses a two-step approach: /search to find candidates, then /videos
    to get full metadata (stats, duration) for filtering and storage.
    """

    platform = "youtube"
    base_url = "https://www.googleapis.com/youtube/v3"
    _duration_re = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
    _hashtag_re = re.compile(r"(?<!\w)#(\w+)")

    def __init__(self, db, region_code: str = "US"):
        super().__init__(db)
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.region_code = region_code  
     

    async def fetch_trending(self, max_results = 20, niche_id = None, query = None) -> list[RawContentItem]:
        search_query = (query or "shorts").strip()

        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            # Step 1: Search for short-duration videos matching the query.
            # The API's "short" filter catches videos ≤4 min; we filter to
            # ≤60s later in _normalize_video to isolate actual Shorts.
            search_data = await self._get(
                client,
                "/search",
                {
                    "part": "snippet",
                    "type": "video",
                    "videoDuration": "short",
                    "q": search_query,
                    "regionCode": self.region_code,
                    "maxResults": max(1, min(max_results, 50))

                },

            )

            # Collect video IDs from search results for the detail lookup
            video_ids = []

            for item in search_data.get("items", []):
                vid = item.get("id", {}).get("videoId")
                if vid:
                    video_ids.append(vid)

            if not video_ids:
                return []

            # Step 2: Fetch full metadata (stats, duration, description) for
            # each video. The /search endpoint doesn't return these.
            videos_data = await self._get(
                client,
                "/videos",
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(video_ids)
                },
            )

            items: list[RawContentItem] = []
            for video in videos_data.get("items", []):
                normalized = self._normalize_video(video, niche_id)
                if normalized is not None:
                    items.append(normalized)
        
        return self.save_items(items)
                


    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Make a GET request to the YouTube API, injecting the API key automatically."""

        params["key"] = self.api_key
        response = await client.get(path, params=params)
        response.raise_for_status()
        data = response.json()

        # YouTube can return 200 OK but still include an error in the JSON body
        if "error" in data:
            message = data["error"].get("message", "Unknown Youtube API Error")
            raise RuntimeError(f"Youtube API Error: {message}")
        return data
    
    def _normalize_video(self, item: dict[str, Any], niche_id: int | None) -> RawContentItem | None:
        """Convert a single YouTube /videos response item into a RawContentItem.

        Returns None if the video is longer than 60 seconds (not a Short).
        """
        video_id = item.get("id")

        # Each /videos item nests data under these three keys
        snippet = item.get("snippet", {})
        details = item.get("contentDetails", {})
        stats = item.get("statistics", {})

        title = snippet.get("title") if isinstance(snippet.get("title"), str) else ""
        description = snippet.get("description") if isinstance(snippet.get("description"), str) else ""

        duration = self._parse_duration(details.get("duration"))
        hashtags = self._extract_hashtags(title, description, snippet.get("tags", []))

        if duration is not None and duration > 60:
            return None
        
        return RawContentItem(
            niche_id=niche_id,
            platform=self.platform,
            platform_content_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            views=self._to_int(stats.get('viewCount')),
            likes=self._to_int(stats.get('likeCount')),
            comments=self._to_int(stats.get('commentCount')),
            shares=0,
            audio_id=None,
            hashtags=hashtags,
            duration_in_seconds=duration,
            content_format="short",
            published_at = self._parse_datetime(snippet.get("publishedAt")),
        ) 
    
    def _parse_duration(self, value: Any) -> int | None:
        """Convert a YouTube ISO 8601 duration string (e.g. 'PT3M22S') to total seconds."""
        if not isinstance(value, str):
            return None 
        
        m = self._duration_re.match(value)
        if not m:
            return 0
        
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        seconds = int(m.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds


    def _extract_hashtags(self, title: str, description: str, tags: Any) -> list[str]:
        """Merge hashtags from title, description, and API tags into a deduplicated list."""
        out: set[str] = set()

        # Pull #hashtags from free text (title + description)
        for text in (title, description):
            out.update(h.lower() for h in self._hashtag_re.findall(text))

        # API tags come without '#' prefix; normalize to match
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    clean = tag.strip().lower().lstrip("#")
                    out.add(clean)

        return sorted(out)
    
    
    def _to_int(self, value: Any) -> int:
        """Safely cast a value to int; YouTube stats are returned as strings."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
        
    def _parse_datetime(self, value: Any) -> datetime | None:
        """Parse YouTube's ISO 8601 timestamp (e.g. '2026-02-20T15:30:00Z')."""
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            return None