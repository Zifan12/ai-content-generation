"""
TikTok scraper backed by the apidojo Apify actor.

Switched from clockworks~tiktok-hashtag-scraper to apidojo/tiktok-scraper
on 2026-05-10. apidojo returns a richer payload (direct video download URL,
hashtags array, multi-language subtitles, POI metadata) and is 16x cheaper.

The normalizer is the project's single trust boundary for Apify field shapes —
downstream code can treat RawContentItem as clean.
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from src.models.trend import RawContentItem
from src.scrapers.base import BaseScraper


SUBTITLES_DIR = Path("data/subtitles")


class TikTokScraper(BaseScraper):
    """
    Apify-backed TikTok hashtag scraper using the apidojo actor.

    Polling cap = poll_interval_seconds * poll_attempts, hard-capped by
    max_duration_seconds.
    """

    platform = "tiktok"
    base_url = "https://api.apify.com/v2"

    def __init__(
        self,
        db: Session,
        actor_id: str = "apidojo/tiktok-scraper",
        poll_interval_seconds: float = 5.0,
        poll_attempts: int = 24,
        max_duration_seconds: int = 120,
    ):
        super().__init__(db)
        self.api_token = os.getenv("APIFY_API_TOKEN")
        self.actor_id = actor_id
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_attempts = poll_attempts
        self.max_duration_seconds = max_duration_seconds

    async def fetch_trending(
        self,
        max_results: int = 50,
        niche_id: int | None = None,
        query: list[str] | None = None,
        keywords: list[str] | None = None,
        sort_type: str = "RELEVANCE",
    ) -> tuple[list[RawContentItem], int, int]:
        """Fetch trending TikTok content via apidojo actor.

        Args:
            max_results: Maximum items to fetch from Apify.
            niche_id: FK to niches table, attached to each saved item.
            query: Hashtag seeds — converted to startUrls (hashtag pages).
                sortType has NO effect on startUrls; TikTok controls ordering.
            keywords: Search keyword terms. sortType applies to these.
                Use alongside or instead of query for sort-controlled results.
            sort_type: One of RELEVANCE, MOST_LIKED, DATE_POSTED.
                Only affects keyword search results, ignored for startUrls.
        """
        if not self.api_token:
            raise RuntimeError("APIFY_API_TOKEN is not set")

        if isinstance(query, list):
            hashtags = query if query else []
        elif query:
            hashtags = [query]
        else:
            hashtags = []

        start_urls = [
            f"https://www.tiktok.com/tag/{tag.lstrip('#')}" for tag in hashtags
        ]

        run_input = {
            "startUrls": start_urls,
            "maxItems": max(1, max_results),
            "keywords": keywords or [],
            "dateRange": "DEFAULT",
            "location": "US",
            "sortType": sort_type,
            "customMapFunction": "(object) => { return {...object} }",
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            run = await self._start_run(client, headers, run_input)
            run_id = run["id"]

            finished_run = await self._poll_run(client, headers, run_id)
            dataset_id = finished_run.get("defaultDatasetId")
            if not dataset_id:
                return []

            dataset_items = await self._fetch_dataset_items(client, headers, dataset_id)

            items: list[RawContentItem] = []
            for raw in dataset_items:
                normalized = self._normalize_item(raw, niche_id)
                if normalized is None:
                    continue
                await self._download_subtitle_if_present(client, normalized)
                items.append(normalized)

            (inserted, updated) = self.upsert_items(items)

        return (items, inserted, updated) 

    async def _start_run(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        run_input: dict[str, Any],
    ) -> dict:
        """POST to Apify to start an actor run; return the run metadata dict."""
        # apidojo expects a tilde-encoded actor id in the URL path
        actor_path = self.actor_id.replace("/", "~")
        response = await client.post(
            f"/acts/{actor_path}/runs",
            headers=headers,
            json=run_input,
            params={"token": self.api_token},
        )
        response.raise_for_status()
        return response.json()["data"]

    async def _poll_run(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        run_id: str,
    ) -> dict:
        """Poll until SUCCEEDED or terminal status; raise TimeoutError if budget exceeded."""
        started = time.monotonic()

        for _ in range(self.poll_attempts):
            if time.monotonic() - started > self.max_duration_seconds:
                raise TimeoutError(
                    f"TikTok Apify run exceeded {self.max_duration_seconds}s"
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
                raise RuntimeError(
                    f"TikTok Apify run ended with status {status}. "
                    f"exitCode={data.get('exitCode')} stats={data.get('stats')}"
                )

            await asyncio.sleep(self.poll_interval_seconds)

        raise TimeoutError(
            f"TikTok Apify run did not finish after {self.poll_attempts} polls"
        )

    async def _fetch_dataset_items(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        dataset_id: str,
    ) -> list[dict]:
        """Fetch all items from a completed Apify dataset; return empty list on non-list response."""
        response = await client.get(
            f"/datasets/{dataset_id}/items",
            headers=headers,
            params={"token": self.api_token, "clean": "true"},
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    async def _download_subtitle_if_present(
        self, client: httpx.AsyncClient, item: RawContentItem
    ) -> None:
        """Eagerly download the picked English subtitle (signed URLs expire ~30 days)."""
        if not item.subtitle_url:
            return
        SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
        target = SUBTITLES_DIR / f"{item.platform_content_id}_en.vtt"
        if target.exists():
            return
        try:
            response = await client.get(item.subtitle_url, timeout=15.0)
            response.raise_for_status()
            target.write_text(response.text, encoding="utf-8")
        except (httpx.HTTPError, OSError):
            # Subtitle archival is best-effort; the URL stays in the row for retry.
            return

    def _normalize_item(
        self, item: dict[str, Any], niche_id: int | None
    ) -> RawContentItem | None:
        # apidojo returns metric/timestamp fields with mostly-consistent types,
        # but we still coerce defensively across runs.
        item_id = item.get("id")
        if not item_id:
            return None

        def _coerce_int(value: Any, default: int = 0) -> int:
            """
            Safely coerce a value to int, with fallback default.
            
            Apify metric fields (views, likes, comments, shares) vary in type
            across scrape runs (sometimes null, sometimes string, sometimes already int).
            This defensive helper ensures consistent int output even if the source
            is malformed, missing, or has unexpected type.
            
            Args:
                value: any value (str, int, None, float, etc.)
                default: fallback if coercion fails (default 0)
            
            Returns:
                int(value) or default if coercion/parsing fails
            """
            try:
                return int(value or 0)
            except (ValueError, TypeError):
                return default

        views = _coerce_int(item.get("views"))
        likes = _coerce_int(item.get("likes"))
        comments = _coerce_int(item.get("comments"))
        shares = _coerce_int(item.get("shares"))
        collect_count = _coerce_int(item.get("bookmarks"))

        hashtags_raw = item.get("hashtags") or []
        seen: set[str] = set()
        hashtags_list: list[str] = []
        for tag in hashtags_raw:
            if not isinstance(tag, str):
                continue
            normalized = tag.lower().lstrip("#").strip()
            if normalized and normalized not in seen:
                hashtags_list.append(normalized)
                seen.add(normalized)
        hashtags_list.sort()

        channel = item.get("channel") or {}
        author_username = channel.get("username") or None
        if author_username is not None:
            author_username = str(author_username)
        author_tiktok_id = channel.get("id")
        if author_tiktok_id is not None:
            author_tiktok_id = str(author_tiktok_id)

        video = item.get("video") or {}
        video_download_url = video.get("url") or None
        video_aspect_ratio = video.get("ratio") or None
        thumbnail_url = video.get("cover") or video.get("thumbnail") or None
        duration_in_seconds = None
        duration_raw = video.get("duration")
        if duration_raw is not None:
            try:
                duration_in_seconds = int(duration_raw)
            except (ValueError, TypeError):
                duration_in_seconds = None

        song = item.get("song") or {}
        song_id = song.get("id")
        audio_id = str(song_id) if song_id is not None else None
        # apidojo does not return a music stream URL — leave music_audio_url None.
        music_audio_url = None

        subtitle_url = None
        subs = item.get("subtitleInformation") or []
        if isinstance(subs, list):
            for sub in subs:
                if not isinstance(sub, dict):
                    continue
                lang_code = str(sub.get("language_code") or "").lower()
                if lang_code.startswith("en"):
                    subtitle_url = sub.get("url")
                    break

        published_at = None
        uploaded_at = item.get("uploadedAt")
        if uploaded_at is not None:
            try:
                published_at = datetime.fromtimestamp(int(uploaded_at), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                published_at = None

        poi = item.get("poi") or {}
        poi_name = poi.get("poiName") or None
        poi_country = poi.get("regionCode") or None
        if poi_country is not None:
            poi_country = str(poi_country)[:8]

        return RawContentItem(
            niche_id=niche_id,
            platform=self.platform,
            platform_content_id=str(item_id),
            url=item.get("postPage") or "",
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            collect_count=collect_count,
            audio_id=audio_id,
            hashtags=hashtags_list,
            duration_in_seconds=duration_in_seconds,
            content_format="video",
            published_at=published_at,
            title=None,
            description=item.get("title"),
            thumbnail_url=thumbnail_url,
            music_audio_url=music_audio_url,
            video_download_url=video_download_url,
            video_aspect_ratio=video_aspect_ratio,
            subtitle_url=subtitle_url,
            author_username=author_username,
            author_tiktok_id=author_tiktok_id,
            poi_name=poi_name,
            poi_country=poi_country,
            input_source=item.get("inputSource"),
            raw_apify_payload=item,
        )
