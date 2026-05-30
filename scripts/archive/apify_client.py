"""
Minimal synchronous Apify client for the apidojo/tiktok-scraper actor.

Standalone copy of the run/poll/fetch dance (the DB-coupled production version
lives in src/scrapers/tiktok.py and is deliberately NOT imported — this tool
must stay decoupled from the live pipeline). Returns raw dataset dicts with no
normalization; the archive writer owns field extraction.
"""

import time
from typing import Any

import httpx

ACTOR_ID = "apidojo/tiktok-scraper"
BASE_URL = "https://api.apify.com/v2"
TERMINAL_BAD = {"FAILED", "ABORTED", "TIMED-OUT"}


class ApifyClient:
    """
    Launch an actor run for one hashtag, poll to completion, fetch the dataset.

    Polling is capped by poll_attempts * poll_interval_seconds and by
    max_duration_seconds, whichever trips first.
    """

    def __init__(
        self,
        token: str,
        poll_interval_seconds: float = 5.0,
        poll_attempts: int = 60,
        max_duration_seconds: int = 600,
        request_timeout: float = 30.0,
    ):
        self.token = token
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_attempts = poll_attempts
        self.max_duration_seconds = max_duration_seconds
        self.request_timeout = request_timeout

    def run_hashtag(
        self,
        hashtag: str,
        max_items: int,
        location: str = "US",
        sort_type: str = "RELEVANCE",
    ) -> list[dict[str, Any]]:
        """
        Scrape one hashtag and return its raw dataset items.

        Args:
            hashtag: tag without '#'.
            max_items: cap passed to the actor (maxItems).
            location: actor location input.
            sort_type: RELEVANCE | MOST_LIKED | DATE_POSTED.

        Returns:
            List of raw item dicts (possibly empty).

        Raises:
            RuntimeError: if the run ends FAILED/ABORTED/TIMED-OUT.
            TimeoutError: if the run does not finish within the poll budget.
            httpx.HTTPStatusError: on a non-2xx API response.
        """
        run_input = {
            "startUrls": [f"https://www.tiktok.com/tag/{hashtag.lstrip('#')}"],
            "maxItems": max(1, max_items),
            "keywords": [],
            "dateRange": "DEFAULT",
            "location": location,
            "sortType": sort_type,
            "customMapFunction": "(object) => { return {...object} }",
        }
        params = {"token": self.token}
        actor_path = ACTOR_ID.replace("/", "~")

        with httpx.Client(base_url=BASE_URL, timeout=self.request_timeout) as client:
            start = client.post(
                f"/acts/{actor_path}/runs", json=run_input, params=params
            )
            start.raise_for_status()
            run_id = start.json()["data"]["id"]

            dataset_id = self._poll(client, run_id, params)
            if not dataset_id:
                return []

            items = client.get(
                f"/datasets/{dataset_id}/items",
                params={**params, "clean": "true"},
            )
            items.raise_for_status()
            body = items.json()
            return body if isinstance(body, list) else []

    def _poll(self, client: httpx.Client, run_id: str, params: dict) -> str | None:
        """Poll the run until SUCCEEDED; return defaultDatasetId or None."""
        started = time.monotonic()
        for _ in range(self.poll_attempts):
            if time.monotonic() - started > self.max_duration_seconds:
                raise TimeoutError(f"Apify run {run_id} exceeded {self.max_duration_seconds}s")
            resp = client.get(f"/actor-runs/{run_id}", params=params)
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data.get("status")
            if status == "SUCCEEDED":
                return data.get("defaultDatasetId")
            if status in TERMINAL_BAD:
                raise RuntimeError(f"Apify run {run_id} ended {status}")
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(f"Apify run {run_id} unfinished after {self.poll_attempts} polls")
