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
        days_back: int = 30,
        poll_interval_seconds: float = 5.0,
        poll_attempts: int = 24,
        max_duration_seconds: int = 120,
    ):
        super().__init__(db)
        self.api_token = os.getenv("APIFY_API_TOKEN")
        self.actor_id = actor_id
        self.days_back = days_back
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_attempts = poll_attempts
        self.max_duration_seconds = max_duration_seconds

    async def fetch_trending(
        self,
        max_results: int = 50,
        niche_id: int | None = None,
        query: str | None = None,
    ) -> list[RawContentItem]:
        if not self.api_token:
            raise RuntimeError("APIFY_API_TOKEN is not set")

        hashtag = query if query else "viral"

        run_input = {
            "hashtags": [hashtag],
            "resultsPerPage": max(1, min(max_results, 500)),
            "profileSorting": "popular",
            "oldestPostDateUnified": str(self.days_back),
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
                raise RuntimeError(f"TikTok Apify run ended with status {status}")

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
        # User writes this — see Task 2
        raise NotImplementedError
