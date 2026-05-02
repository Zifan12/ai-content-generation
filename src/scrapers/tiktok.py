import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from src.models.trend import RawContentItem
from src.scrapers.base import BaseScraper


class TikTokScraper(BaseScraper):

    platform = "tiktok"
    base_url = "https://api.apify.com/v2"

    def __init__(
        self,
        db: Session,
        actor_id: str = "clockworks~tiktok-hashtag-scraper",
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
    ) -> list[RawContentItem]:
        if not self.api_token:
            raise RuntimeError("APIFY_API_TOKEN is not set")

        if isinstance(query, list):
            hashtags = query if query else ["viral"]
        elif query:
            hashtags = [query]
        else:
            hashtags = ["viral"]

        run_input = {
            "hashtags": hashtags,
            "resultsPerPage": max(1, min(max_results, 800)),
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

        items = []
        for item in dataset_items:
            normalized = self._normalize_item(item, niche_id)
            if normalized is not None:
                items.append(normalized)

        return self.save_items(items)

    async def _start_run(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        run_input: dict[str, Any],
    ) -> dict:
        response = await client.post(
            f"/acts/{self.actor_id}/runs",
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
        response = await client.get(
            f"/datasets/{dataset_id}/items",
            headers=headers,
            params={"token": self.api_token, "clean": "true"},
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _normalize_item(
        self, item: dict[str, Any], niche_id: int | None
    ) -> RawContentItem | None:
        # Apify scraper returns metric/timestamp fields with inconsistent types
        # (str | int | None) across runs — coerce defensively rather than trust schema.
        item_id = item.get("id")
        if not item_id:
            return None

        url = item.get("webVideoUrl") or item.get("videoUrl")

        try:
            views = int(item.get("playCount") or 0)
        except (ValueError, TypeError):
            views = 0

        try:
            likes = int(item.get("diggCount") or 0)
        except (ValueError, TypeError):
            likes = 0

        try:
            comments = int(item.get("commentCount") or 0)
        except (ValueError, TypeError):
            comments = 0

        try:
            shares = int(item.get("shareCount") or 0)
        except (ValueError, TypeError):
            shares = 0

        # Extract audio ID from nested musicMeta
        audio_id = None
        music_meta = item.get("musicMeta")
        if music_meta and isinstance(music_meta, dict):
            music_id = music_meta.get("musicId")
            if music_id:
                audio_id = str(music_id)

        # Extract duration from nested videoMeta
        duration_in_seconds = None
        video_meta = item.get("videoMeta")
        if video_meta and isinstance(video_meta, dict):
            try:
                duration = video_meta.get("duration")
                if duration is not None:
                    duration_in_seconds = int(duration)
            except (ValueError, TypeError):
                pass

        # Extract and normalize hashtags
        hashtags_list: list[str] = []
        hashtags_raw = item.get("hashtags")
        if hashtags_raw and isinstance(hashtags_raw, list):
            seen = set()
            for hashtag_obj in hashtags_raw:
                if isinstance(hashtag_obj, dict):
                    name = hashtag_obj.get("name")
                    if name:
                        # Lowercase, strip leading #, and deduplicate
                        normalized = name.lower().lstrip("#")
                        if normalized and normalized not in seen:
                            hashtags_list.append(normalized)
                            seen.add(normalized)
            # Sort the hashtags
            hashtags_list.sort()

        # Extract published_at from createTime
        published_at = None
        create_time = item.get("createTime")
        if create_time is not None:
            try:
                published_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

        return RawContentItem(
            niche_id=niche_id,
            platform=self.platform,
            platform_content_id=str(item_id),
            url=url,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            audio_id=audio_id,
            hashtags=hashtags_list,
            duration_in_seconds=duration_in_seconds,
            content_format="video",
            published_at=published_at,
        )

