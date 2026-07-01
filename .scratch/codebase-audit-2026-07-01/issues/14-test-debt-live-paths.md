# Test-suite blind spots track exactly the live path

Status: needs-triage
Severity: High (AUD-H13; systemic bundle)

Ranked by "which tests would pass while the live loop is broken":

- (f) **ROOT CAUSE:** 14 test files run on `sqlite:///:memory:` against an ADR-0006 Postgres-only app — the mechanism that hid BUG-006 (sqlite-dialect upsert). Direction: a small `@pytest.mark.postgres` integration tier against the existing compose service on :5433, covering upsert / JSON semantics / pgvector paths. Everything else in this bundle is cheaper after this exists.
- (a) `ApifyRedditScraper` — the class `pitch_angles.py` actually instantiates — has ZERO tests; only the superseded praw `RedditScraper` is tested. Port the fake-client pattern via the existing `item_fetcher` seam: `_items_to_events` postId/`t3_` bucketing, `_top_comments` depth-filter + upvote sort, `_build_run_input`.
- (b) `executor.py` real path untested (only dry-run). Fakes for `run_cli`/`download`/`probe_audio` already exist as parameters — assert still-URL flows into motion `--image`, `_parse_credits`/`_extract_url` raise on garbage, audio-mismatch warning fires.
- (c) No test anywhere exercises an LLM-boundary failure — every suite fakes at `.llm.parse()`. One test where `client.messages.parse` raises; one asserting `parse_with_raw`'s raw-meta dict keys (cost-accounting input).
- (d) `reddit_search` $1.00 guard trip + missing-token paths (the BUG-003 fix) untested; same for `tavily_search` missing-key.
- (e) Shipped-then-fixed `--no-llm` ordering regression (commit 1e129eb) has no regression test; extract the ordering into a testable predicate or monkeypatch constructors to raise.
- (g) `tracing.py` untested despite BUG-001 having lived there — one test mocking `langfuse.observe` asserting `as_type=kind` passthrough.
- (h) Zero coverage: `instagram.py`, `api/app.py`, `enrichment/transcripts.py` (pure-string parse logic, cheapest win).
- (i) `test_angle_pitcher.py:75-78` fake embedder returns fixed orthogonal vectors → diversity-warning branch unreachable by any assertion; parametrize with near-identical vectors + caplog.
- (j) `test_database_url.py:48-51` docstring claims a CI skip that doesn't exist in code — add the skip guard or fix the docstring.

Needs-triage: user decides sequencing (most items are learning-scope test code the user writes); recommendation is (f) first, then (a) and (d) — they guard money and the live loop.

## Comments
