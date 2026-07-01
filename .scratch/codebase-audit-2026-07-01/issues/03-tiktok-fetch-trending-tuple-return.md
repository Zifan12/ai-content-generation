# tiktok.py: early return violates the 3-tuple contract

Status: ready-for-agent
Severity: Critical (AUD-C4)

`src/scrapers/tiktok.py:111-112` returns a bare `[]` inside `fetch_trending() -> tuple[list[RawContentItem], int, int]`. Both callers unpack three values (`src/scrapers/recurring.py:103`, `scripts/run_scrape.py:81`) — an Apify run finishing without `defaultDatasetId` raises `ValueError: not enough values to unpack`, which recurring.py's broad except then hides (see issue 02).

Fix direction: `return ([], 0, 0)`. Verification: `uv run mypy src/scrapers/` should flag/confirm; add a unit test with a fetcher stub returning a run dict without `defaultDatasetId`.

Adjacent (fold into the same PR as BUG-006's dialect fix): the post-upsert refetch at `tiktok.py:126-129` filters only `platform_content_id` without the `platform` predicate (AUD-M14).

## Comments
