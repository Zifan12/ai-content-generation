# TikTok Scraper Design

**Date:** 2026-04-25
**Phase:** 0 — Data Collection
**Status:** Approved

---

## Goal

Build `src/scrapers/tiktok.py` to collect high-performing TikTok videos by hashtag seed, storing them as `RawContentItem` rows for downstream ML virality predictor training.

---

## Strategy

Scrape top-performing videos from the past 30 days per hashtag seed, sorted by popularity. Hashtag seeds come from the `niches.hashtag_seeds` DB column. This is training data accumulation — volume and signal quality matter, not real-time freshness.

---

## Apify Actor

**Actor:** `clockworks~tiktok-hashtag-scraper`
**Cost:** ~$2–5 / 1K results
**Source:** Main TikTok platform (not Creative Center — organic user videos)

### Actor input
```json
{
  "hashtags": ["gymtok"],
  "resultsPerPage": 50,
  "profileSorting": "popular",
  "oldestPostDateUnified": "30"
}
```

- `resultsPerPage` = `max_results` from `fetch_trending`, capped at 500 (actor hard limit)
- `profileSorting: "popular"` — highest engagement first
- `oldestPostDateUnified` = `days_back` constructor arg (default 30), passed as string
- `hashtags` = `[query]` where `query` is one hashtag seed from `fetch_trending`

---

## Architecture

Same pattern as `InstagramScraper`: start Apify run → poll until SUCCEEDED → fetch dataset → normalize items → save via `BaseScraper.save_items`.

No new base class methods needed.

---

## Class Interface

```python
class TikTokScraper(BaseScraper):
    platform = "tiktok"

    def __init__(
        self,
        db,
        actor_id: str = "clockworks~tiktok-hashtag-scraper",
        days_back: int = 30,
        poll_interval_seconds: float = 5.0,
        poll_attempts: int = 24,
        max_duration_seconds: int = 120,
    )

    async def fetch_trending(
        self, max_results: int = 50, niche_id: int | None = None, query: str | None = None
    ) -> list[RawContentItem]

    async def _start_run(self, client, headers, run_input) -> dict
    async def _poll_run(self, client, headers, run_id) -> dict
    async def _fetch_dataset_items(self, client, headers, dataset_id) -> list[dict]
    def _normalize_item(self, item: dict, niche_id: int | None) -> RawContentItem | None
```

`query` in `fetch_trending` is a single hashtag seed string (e.g. `"gymtok"`). The scheduler calls this once per seed per niche.

---

## Field Mapping (Actor output → RawContentItem)

| Actor field | RawContentItem field | Notes |
|---|---|---|
| `id` | `platform_content_id` | TikTok video ID |
| `webVideoUrl` / `videoUrl` | `url` | Try both keys |
| `playCount` | `views` | |
| `diggCount` | `likes` | TikTok's name for hearts/likes |
| `commentCount` | `comments` | |
| `shareCount` | `shares` | |
| `musicMeta.musicId` | `audio_id` | Nested field |
| `hashtags` (list) | `hashtags` | Already a list, normalize to lowercase |
| `videoMeta.duration` | `duration_in_seconds` | Nested field, int seconds |
| `createTime` | `published_at` | Unix timestamp |
| — | `content_format = "video"` | Hardcoded |
| — | `platform = "tiktok"` | Class attribute |

---

## Who Writes What

| Part | Who | Why |
|---|---|---|
| `__init__`, `fetch_trending`, `_start_run`, `_poll_run`, `_fetch_dataset_items` | AI writes | Boilerplate identical to Instagram scraper — low learning value |
| `_normalize_item` | User writes | Core learning: read unfamiliar API response, pick right fields, handle missing data |

---

## Error Handling

- Missing `id` field → return `None` from `_normalize_item` (skip item)
- Apify run FAILED/ABORTED/TIMED-OUT → raise `RuntimeError`
- Poll timeout → raise `TimeoutError`
- Duplicate `(platform, platform_content_id)` → silently skipped by `BaseScraper.save_items`

---

## Testing

Manual test script `test_tiktok.py` (mirrors `test_instagram.py`):
- Call `fetch_trending(max_results=10, query="gymtok")`
- Assert returned list is non-empty
- Print first item's views/likes to confirm real data

No unit tests for Phase 0 — integration test against live Apify is sufficient at this stage.

---

## Out of Scope

- Instagram hashtag scraper rewrite (separate task)
- Scheduler integration (already scaffolded in `src/scrapers/scheduler.py`)
- Date window configurability via API endpoint (hardcoded 30 days for now)
