# TikTok Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/scrapers/tiktok.py` using the `clockworks~tiktok-hashtag-scraper` Apify actor to collect high-performing TikTok videos by hashtag seed and store them as `RawContentItem` rows.

**Architecture:** Same pattern as `InstagramScraper` — start Apify run → poll until SUCCEEDED → fetch dataset → normalize items → save. AI writes the scaffold (boilerplate); user writes `_normalize_item` (the learning exercise).

**Tech Stack:** Python 3.13+, httpx (async HTTP), SQLAlchemy 2.0, Apify REST API, python-dotenv

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/scrapers/tiktok.py` | Create | TikTokScraper class — full scraper implementation |
| `test_tiktok.py` | Create | Manual integration test against live Apify |

No other files need modification — `BaseScraper`, `RawContentItem`, and `SessionLocal` are already defined and don't need changes.

---

## Task 1: Scaffold `src/scrapers/tiktok.py` with everything except `_normalize_item`

**Files:**
- Create: `src/scrapers/tiktok.py`

AI writes this task. You read and understand it — that's the goal.

- [ ] **Step 1: Create the file with imports and class skeleton**

```python
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
        # YOU WRITE THIS — see Task 2
        raise NotImplementedError
```

- [ ] **Step 2: Verify the file imports cleanly (no _normalize_item needed yet)**

```bash
uv run python -c "from src.scrapers.tiktok import TikTokScraper; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit the scaffold**

```bash
git add src/scrapers/tiktok.py
git commit -m "feat: add TikTok scraper scaffold (normalize_item stub)"
```

---

## Task 2: Write `_normalize_item` (user writes this)

**Files:**
- Modify: `src/scrapers/tiktok.py` — replace the `NotImplementedError` stub

This is your exercise. The Apify actor returns raw dicts — you map them to `RawContentItem`.

**What to know before starting:**

The actor response for one video looks roughly like this (fields that matter):

```json
{
  "id": "7345678901234567890",
  "webVideoUrl": "https://www.tiktok.com/@user/video/7345678901234567890",
  "videoUrl": "https://...",
  "playCount": 1200000,
  "diggCount": 84000,
  "commentCount": 3200,
  "shareCount": 9100,
  "createTime": 1713916800,
  "hashtags": [
    {"name": "gymtok"},
    {"name": "fitness"}
  ],
  "musicMeta": {
    "musicId": "6831234567890123456",
    "musicName": "original sound"
  },
  "videoMeta": {
    "duration": 28
  }
}
```

Key things to handle:
- `id` missing → return `None` (skip the item entirely)
- `webVideoUrl` preferred over `videoUrl` — try `webVideoUrl` first, fall back to `videoUrl`
- `hashtags` is a **list of dicts** with a `"name"` key — not a list of strings. Extract `item["name"]` from each, lowercase it, strip `#`
- `musicMeta` and `videoMeta` are nested dicts — use `.get()` to avoid KeyError
- `createTime` is a Unix timestamp (int) — convert to `datetime` with `datetime.fromtimestamp(value, tz=timezone.utc)`
- All int fields (`playCount`, `diggCount`, etc.) may be missing — default to `0`

- [ ] **Step 1: Replace the stub with your implementation**

Replace:
```python
    def _normalize_item(
        self, item: dict[str, Any], niche_id: int | None
    ) -> RawContentItem | None:
        # YOU WRITE THIS — see Task 2
        raise NotImplementedError
```

With your implementation. Signature must stay identical. Return `None` for items missing `id`. Return a `RawContentItem` for valid items.

`RawContentItem` fields to populate:

```python
RawContentItem(
    niche_id=niche_id,
    platform=self.platform,          # "tiktok"
    platform_content_id=...,         # str(item["id"])
    url=...,                         # webVideoUrl or videoUrl
    views=...,                       # playCount
    likes=...,                       # diggCount
    comments=...,                    # commentCount
    shares=...,                      # shareCount
    audio_id=...,                    # musicMeta.musicId (str or None)
    hashtags=...,                    # list of lowercase strings, no "#"
    duration_in_seconds=...,         # videoMeta.duration (int or None)
    content_format="video",
    published_at=...,                # datetime from createTime unix ts
)
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -c "from src.scrapers.tiktok import TikTokScraper; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/scrapers/tiktok.py
git commit -m "feat: implement TikTok scraper _normalize_item"
```

---

## Task 3: Create integration test script and run it

**Files:**
- Create: `test_tiktok.py`

- [ ] **Step 1: Create the test script**

```python
import asyncio
from dotenv import load_dotenv

load_dotenv("config/.env")

from src.database import SessionLocal
from src.scrapers.tiktok import TikTokScraper


async def main():
    db = SessionLocal()
    try:
        scraper = TikTokScraper(db)
        print("Starting TikTok scrape...")
        items = await scraper.fetch_trending(max_results=10, query="gymtok")
        print(f"Saved {len(items)} items to DB")
        for item in items:
            print(f"  [{item.platform_content_id}] views={item.views} likes={item.likes} hashtags={item.hashtags[:3]}")
    finally:
        db.close()


asyncio.run(main())
```

- [ ] **Step 2: Run it**

```bash
uv run python test_tiktok.py
```

Expected output (values will differ):
```
Starting TikTok scrape...
Saved 10 items to DB
  [7345678901234567890] views=1200000 likes=84000 hashtags=['gymtok', 'fitness', 'workout']
  ...
```

If you see `Saved 0 items to DB` — the run likely succeeded but `_normalize_item` returned `None` for everything. Print the raw first item to debug:

```python
# Add temporarily to fetch_trending, before the normalize loop:
if dataset_items:
    import json
    print(json.dumps(dataset_items[0], indent=2, default=str))
```

This shows you the real field names the actor returns — use them to fix your field mapping.

- [ ] **Step 3: Commit once output looks correct**

```bash
git add test_tiktok.py
git commit -m "test: add TikTok integration test script"
```

---

## Self-Review Notes

- Spec requires `clockworks~tiktok-hashtag-scraper` — used in `actor_id` default. ✓
- Spec requires `profileSorting: "popular"` — present in `fetch_trending`. ✓
- Spec requires `oldestPostDateUnified` = `days_back` as string — `str(self.days_back)` used. ✓
- Spec requires `resultsPerPage` = `max_results` capped at 500 — `max(1, min(max_results, 500))` used. ✓
- Spec requires `hashtags` field normalized to lowercase — noted in Task 2 instructions. ✓
- Spec field mapping: all 10 fields covered in Task 2. ✓
- Spec "who writes what": scaffold in Task 1 (AI), `_normalize_item` in Task 2 (user). ✓
- No placeholders, no TBDs, all code complete. ✓
