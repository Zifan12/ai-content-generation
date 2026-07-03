# Bug Log

Track every shipped feature that fails, what was tried, and what fixed it.

## Status Legend
- `open`: issue is reproducible and unresolved
- `monitoring`: fix shipped, observing behavior
- `closed`: fix verified

## Entries

### BUG-001 - traced() drops the `kind` arg → LLM calls log as spans, not generations
- Date opened: 2026-06-14
- Status: closed
- Feature: Langfuse observability (`src/observability/tracing.py`), affects EVERY `@traced` LLM call (extractor, writer, judge)
- Environment: Langfuse US cloud (live — `get_client().auth_check()` returns True with config/.env keys)
- Error/behavior: `traced(name=..., kind="generation")` accepts `kind` but never forwards it.
  Line 31 calls `observe(name=..., capture_input=..., capture_output=...)` with no `kind`. So
  calls decorated `@traced(kind="generation")` (e.g. `anthropic_llm.parse`) likely record as
  plain SPANS, not GENERATIONS. Token/cost/`cache_read_input_tokens` are generation-specific
  fields → suspected missing on these spans. This is the suspected reason the Opus 4.8 cache
  question (cache_read vs 4096-token min) has never had a clean dashboard answer.
- Reproduction steps:
1. Run any traced LLM call (e.g. `run_rubric_eval --fixtures data/golden/writer_floor_static.jsonl`).
2. Open the Langfuse dashboard, find the `anthropic_llm.parse` observation.
3. Check whether it is typed GENERATION and whether token/cache fields are populated.
- Attempted fixes:
1. (logged 2026-06-14, deferred per scope; surfaced during the judge-floor-probe feature)
2. (2026-06-14) Confirmed via context7 that the langfuse Python v3/v4 SDK `observe()` takes
   `as_type` (NOT `kind`, NOT `type`); valid values include "generation". Forwarded the
   decorator's `kind` arg through as `observe(..., as_type=kind)` on line 31. Default
   `kind="span"` is accepted by langfuse (verified by import smoke-test, no error).
- Root cause: CONFIRMED — `kind` was plumbed into `traced()` but never passed to
  `langfuse.observe`. The SDK param is named `as_type`, so even a literal passthrough of
  `kind=` would have raised TypeError; the rename was required.
- Final fix: `src/observability/tracing.py:31` — `observe(name=..., capture_input=...,
  capture_output=..., as_type=kind)`.
- Date fixed: 2026-06-14
- Validation evidence: 3 back-to-back floor-probe runs (`run_rubric_eval --fixtures ...`),
  dashboard JSON read on each `anthropic_llm.parse` observation:
  - `"type": "GENERATION"` (was logging as span before) ✅
  - token fields now present: `usage_input_tokens`, `usage_output_tokens` ✅
  - cache lifecycle captured end-to-end — run 1 (cold): `cache_read=0, cache_write=2032`;
    run 2 (warm, +8min): `cache_read=2032, cache_write=0`; run 3 (warm, +17s):
    `cache_read=2032, input_tokens=1` (full rubric prefix served from cache).
  Closes the long-carried Opus-4.8 cache question: prompt caching IS live; warm read = 2032.
  Full pytest suite still green (237 passed, 1 skipped) — no regression from the signature change.

### BUG-003 - `reddit_search` (Path B) has no cost guard and its item cap is silently ignored
- Date opened: 2026-06-30
- Status: monitoring
- Feature: `src/monitor/tools/reddit_search.py` (Task 4, User-Topic Context Agent) — called by
  `ContextAgent._act_reddit` on every `--topic` run, up to `max_tool_calls` (5) times per run.
- Environment: Apify `harshmaur/reddit-scraper` actor, search mode (`searchTerms`), live
  `APIFY_API_TOKEN`.
- Error/behavior: two compounding gaps.
  1. **No cost guard.** The Task 4 plan explicitly calls for "Apply the $1.00 cost guard before
     the call" — never implemented. `reddit_search()` calls Apify unconditionally.
  2. **Cap silently ignored.** The tool passes `"maxItems": max_items` (default 20) to the actor.
     `ApifyRedditScraper` (the working subreddit-listing path in `scraper.py`) uses
     `maxPostsCount` + `maxCommentsPerPost` for this same actor instead — `maxItems` is
     suspected not to be a field this actor honors in search mode. Observed Apify datasets from
     tonight's testing consistently sized ~165-210 items per call, ~10x the configured cap.
  3. **False safety comment.** `pitch_angles.py`'s own `$1.00` guard in `main()` is explicitly
     skipped for `--topic` runs, with a comment claiming reddit_search is "cost-guarded inside
     the tool itself" — untrue, and this claim was repeated to the user without verifying it
     against `reddit_search.py`, allowing several more live runs before the gap was caught.
- Reproduction steps:
  1. Run `uv run python -m scripts.pitch_angles --topic "<any topic>"` a few times.
  2. Open Apify Console → Storage → Datasets, sorted by Modified desc.
  3. Compare item counts against the tool's `max_items=20` default — counts run ~165-210.
- Root cause: Task 4's planned guard was never implemented; the actor param name was assumed
  (not verified against the actor's real search-mode schema, unlike the listing-mode path which
  was already correct); the false "self-guarded" comment in `pitch_angles.py` let this go
  unnoticed through several runs.
- Attempted fixes:
  1. (2026-06-30) Looked up the actor's real pricing (`apify.com/harshmaur/reddit-scraper` page
     metadata, confirmed 4x identically): "From $2/1,000 results" = $0.002/item — NOT the
     $0.001844/item constant used elsewhere for a different actor; did not reuse it blind.
  2. (2026-06-30) `reddit_search.py`: renamed `max_items` → `max_posts`, changed the actor field
     from `maxItems` to `maxPostsCount` (matches both the Task 4 plan's own spec and the working
     `ApifyRedditScraper` listing-mode pattern). Added a pre-call cost guard — estimates
     `max_posts × (1 + max_comments_per_post)` items × $0.002/item, raises `RuntimeError` before
     any network call if estimate exceeds $1.00. Guard is skipped only when a test `item_fetcher`
     is injected (same bypass pattern as the existing token check — no real spend in tests).
- Date fixed: 2026-06-30 (code); live-validated 2026-07-01.
- Validation evidence: Apify Console billing confirmed **$3.22** actual spend for the incident
  night (bucketed under 2026-07-01 UTC) — real, but well below the ~$9-12 worst-case estimated
  from raw dataset item counts before checking the authoritative billing page. Post-fix: 70/70
  monitor tests pass, ruff clean, guard manually confirmed to raise (not silently pass) on an
  oversized request ($5.10 estimate, 50×50) without hitting the network; defaults (20 posts × 20
  comments = 420 items ≈ $0.84) stay under the $1.00 threshold so normal runs are unaffected.
  **Live validation (2026-07-01):** a real `--topic` run produced Apify datasets sized exactly
  420 items each (pulled via `GET /v2/datasets/{id}/items`, not just the console item count) —
  matches the intended `max_posts × (1 + max_comments_per_post)` cap, not the old ~165-210-per-call
  (~10x-over) blowup. `maxPostsCount` is honored in search mode. Moving to `closed`.

### BUG-004 - `reddit_search`'s `searchSort: "top"` silently ignores `searchTerms` — returns unrelated Reddit-wide top posts
- Date opened: 2026-07-01
- Status: closed
- Feature: `src/monitor/tools/reddit_search.py`, the `searchSort` run-input field.
- Environment: Apify `harshmaur/reddit-scraper` actor, search mode, live `APIFY_API_TOKEN`.
- Error/behavior: switched `searchSort` from `"relevance"` to `"top"` (per the actor's own
  documented input schema, which lists `"top"` as a valid search-mode sort value) to satisfy a
  "give me the highest-upvoted matching posts" request. Live `--topic "Wistoria Elfie Zeovs Will
  choice"` run instead returned posts with **zero connection to the query** across all 3 calls
  made that run: r/pics ("Restaurant closed, for good reason"), r/MadeMeSmile (a cancer-survivor
  story), r/OnePiece (Gorosei tarot-card theory). Not dilution — total non-match.
- Reproduction steps:
  1. Set `"searchSort": "top"` in `reddit_search.py`'s run_input.
  2. Run `uv run python -m scripts.pitch_angles --topic "<any specific topic>"`.
  3. Pull the resulting dataset's items via the Apify API and check post titles/subreddits
     against the topic — they will not match.
- Root cause: CONFIRMED via a differential comparison on real paid data (not doc-reading) —
  pulled an earlier same-night dataset that was still on `"relevance"` sort; its #1 result was
  genuinely on-topic ("An infinite tie stalemate! Zeo Vs. Elfie?" in r/Wistoria). `"relevance"`
  correctly filters by `searchTerms`; `"top"` does not — it almost certainly routes to a generic
  "top posts" listing internally, ignoring the query entirely, despite the actor's documented
  schema listing it as a valid *search-mode* sort value. Same failure class as BUG-003's
  `maxItems` gap: documented actor behavior does not match actual behavior; only a live paid
  probe caught it, not the schema page.
- Attempted fixes:
  1. (2026-07-01) Reverted `searchSort` from `"top"` back to `"relevance"` in
     `reddit_search.py`. No cost-guard or formula changes needed — this was a pure value
     regression, not a cap/pricing issue.
- Final fix: `src/monitor/tools/reddit_search.py` — `"searchSort": "relevance"`, with a comment
  documenting the confirmed actor behavior gap so it isn't retried blind.
- Date fixed: 2026-07-01
- Validation evidence: 7/7 `test_tools.py` passing, ruff clean. Not re-run live post-revert
  (would cost more real money to re-confirm what the differential comparison already showed);
  the differential itself — same actor, same night, `"relevance"` sort's real result was on-topic
  and `"top"` sort's real result was not — is the validation evidence.
- **Follow-up (2026-07-01, same day): `"top"` + `withinCommunity` together does work.** Built a
  standalone probe (`scripts/probe_reddit_sort_community.py`) and ran two live paid checks:
  (1) `"top"` + `within_community="r/Wistoria"` + real query → 3 on-topic, upvote-ordered posts
  (scores 312/275/245); (2) same community, garbage query → 0 posts, proving `searchTerms` is
  respected once scoped (rules out "top-of-subreddit-regardless-of-query" as the explanation).
  So the bug is specific to the *unscoped* case — scoping to a known community fixes it.
  `reddit_search.py`'s `searchSort` is now conditional: `"top"` when `within_community` is set,
  `"relevance"` otherwise. Regression tests added in `test_tools.py`
  (`test_reddit_search_sort_defaults_to_relevance_when_unscoped`,
  `test_reddit_search_sort_switches_to_top_when_scoped`); 11/11 `test_tools.py` passing.

### BUG-007 - Anthropic "Grammar compilation timed out" 400 kills a paid pitch run at the first LLM call
- Date opened: 2026-07-01
- Status: monitoring
- Feature: every structured-output LLM call via `src/providers/llm/anthropic_llm.py` `parse_with_raw`
  (`client.messages.parse`); surfaced in `EventExtractor._dedup` (the pipeline's first LLM call) on a
  live `pitch_angles --dry-run`.
- Environment: Anthropic API, model `claude-sonnet-5`, native structured output (`output_format`).
- Error/behavior: `anthropic.BadRequestError: 400 {'type': 'invalid_request_error', 'message':
  'Grammar compilation timed out.'}` (request id req_011Ccc76u6kVk73BMLgB4JFh). The response-schema
  was `DedupVerdict` — a single bool — so schema complexity cannot be the cause; this is the
  server-side constrained-decoding grammar compiler timing out transiently, misreported as a
  non-retryable 400. Because the shared LLM seam had no retry (audit AUD-M6 predicted exactly this)
  the whole run died AFTER the Apify scrape had already been paid (~$0.56, 282 items) — orphaned
  spend, since scraped events lived only in memory.
- Reproduction steps: not deterministic (transient server-side). Any `messages.parse` call can hit it;
  first-seen on a cold run ~7s in.
- Root cause: two layers. (a) Transient Anthropic-side grammar-compiler timeout dressed as a 400.
  (b) Our seam treated all 400s as fatal and the pipeline has no checkpoint between the paid scrape
  and the LLM stages.
- Attempted fixes:
  1. (2026-07-01) `anthropic_llm.py`: bounded retry (2 retries, 2s backoff) ONLY when a
     BadRequestError message contains "Grammar compilation timed out" — grammar is cached
     server-side after a successful compile, so a retry normally clears it. All other 400s still
     raise immediately.
  2. (2026-07-01) `scripts/pitch_angles.py`: `--from-dataset <id>` replay flag — feeds an EXISTING
     Apify dataset through `ApifyRedditScraper`'s `item_fetcher` seam via a free GET (Bearer header,
     not URL token), skipping the actor run and the cost guard (nothing to guard). Recovers a
     crashed run's already-paid scrape; the incident dataset (`tLYHyfiWxQyRNl9jG`, 282 items) is
     replayable.
- Validation evidence: 83/83 tests (monitor+providers) pass, ruff clean. Move to closed after the
  replay run completes end-to-end (which also exercises the retry path if the flake recurs).

### BUG-002 - First reaction-driven render (Stellar Blade "adult redesign") failed the post gate
- Date opened: 2026-06-27
- Status: closed (lessons captured; triggered the hand-first → build-pipeline re-sequencing)
- Feature: Phase-0 hand-made postable video. Render path = `nano_banana_2` still → `kling3_0` i2v ×2 → ffmpeg assemble + Sonilo music + drawtext captions. Artifacts in `render_taste_test/evie_redesign/`.
- Environment: Higgsfield CLI (max plan); Windows ffmpeg. ~22.8cr spent.
- Error/behavior: produced a 12.6s video but the user (binding judge) refused to post. Four distinct failures:
  1. TIMING (the killer): wave was COLD — Stellar Blade: Blood Rain reveal was ~June 6 (Summer Game Fest); we rendered June 27, the discourse had already passed. The idea-fit gate as run only checked recognizable + fictional, NOT heat/recency.
  2. GROUNDING: no reference image used; still generated from a text description → wrong primary outfit (rendered the black poncho; her signature look is the pure-white suit) and the face did not read as Evie.
  3. SHOTCRAFT: both beats frontal/medium and static — no angle/distance variety (violates `render_taste_test/SHOT_CRAFT_CHEATSHEET.md` "vary the distance" / establish-detail-reveal).
  4. CAPTIONS: explainer captions on shots 2-3 were unnecessary; only the hook card earned its place.
  Overall read: "AI slop at a glance."
- Root cause: two layers. (a) Idea-fit gate missing a heat/recency check. (b) The render run took the cheapest ungrounded path (no refs, single frontal still, cheapest model) — so the quality failures are METHOD, not a proven ceiling.
- Final fix (process, not code):
  - Render MECHANICS confirmed working (chain executes end-to-end, identity holds across i2v) → render leaf is de-risked.
  - DROPPED the "hand-make one postable video first" gate (spec §8 / plan Phase 0). The remaining failures are upstream PIPELINE stages, not render-leaf risks, so they can only be fixed by building those stages.
  - Re-sequenced to build the pipeline, attacking failures in order: Stage A harvester WITH heat/recency + idea-fit scoring → Stage C reference-grounded render (real key-art into nano-banana + multi-angle stills) → Stage B story-craft pitcher → loop.
  - Added constraints: reference-grounding mandatory; angle variety; caption restraint; and VERIFY EACH STAGE (test thoroughly on real data) before advancing.
- Date fixed: 2026-06-27
- Validation evidence: the non-slop render METHOD will be proven the first time Stage C runs with real references (not a separate hand-run). Each pipeline stage carries its own verification gate in the plan — no stage is "done" until proven on real data.
- Grounded A/B re-run verdict (2026-07-01, ~28.5cr, `render_taste_test/evie_grounded/`, C-lite spike): reference-grounding CONFIRMED as the fix for BUG-002 failure #2 — feeding real Blood Rain key-art into nano-banana produced a recognizably-Eve character in the correct pure-white armored suit (vs the ungrounded black-poncho/generic-face failure). Grounding hypothesis validated; single changed variable flipped wrong→right. NEW finding surfaced by the binding-judge close inspection: face AND fine suit-panel design drift shot-to-shot because the 3 stills are independently generated and nano-banana has no seed — a cross-shot CONSISTENCY problem, distinct from "can we render the IP at all." Reassigned to Stage C / writer spec; candidate fixes = Higgsfield Soul ID (trained locked identity), Kling multi-shot-in-one-generation, or a seed-capable still model. A ref-iteration is the wrong tool (refs can't seed-lock independent gens). Full pre-registered rubric + verdict: `render_taste_test/evie_grounded/PLAN.md` §8.

### BUG-005 - `pitch_angles` Path A cost guard uses a per-item rate BUG-003 already disproved
- Date opened: 2026-07-01 (found by full-codebase audit, `docs/audits/2026-07-01-full-codebase-audit.md` AUD-H1)
- Status: monitoring
- Feature: `scripts/pitch_angles.py` `main()` Apify cost guard (Path A, non-`--topic` runs) — the
  guard that decides whether a scrape run is allowed to spend at all.
- Environment: Apify `harshmaur/reddit-scraper` actor, listing mode via `ApifyRedditScraper`,
  live `APIFY_API_TOKEN`.
- Error/behavior: `pitch_angles.py:443` sets `_APIFY_COST_PER_ITEM = 0.001844`. BUG-003's
  investigation confirmed (4x, from the actor's own pricing metadata) that `harshmaur/reddit-scraper`
  bills **$0.002/item**, and `src/monitor/tools/reddit_search.py:29-31` explicitly documents that
  the $0.001844 figure belongs to a DIFFERENT actor and must not be reused. Same actor, two rates:
  the search-mode tool guards at $0.002 while the listing-mode guard in `main()` guards at $0.001844
  — an ~8% under-estimate, so configurations estimating just under $1.00 actually cost over it.
  `src/monitor/scraper.py:113` (ApifyRedditScraper docstring) repeats the same wrong rate.
- Reproduction steps:
  1. Read `scripts/pitch_angles.py:443` and `src/monitor/tools/reddit_search.py:29-31` side by side.
  2. Compute the default-run estimate both ways: 7 subs × 4 posts × 11 items = 308 items →
     $0.568 (wrong rate) vs $0.616 (confirmed rate).
  3. Any flag combination whose wrong-rate estimate lands in ($0.92, $1.00] passes the guard while
     its true cost exceeds the $1.00 threshold.
- Root cause: the guard predates BUG-003's pricing confirmation and was never updated when the
  correct rate was established for the tool path; the rate exists as two (three, counting the
  scraper docstring) independent literals instead of one imported constant — the same
  single-source failure class as BUG-003/BUG-004.
- Attempted fixes:
  1. (2026-07-01) `scripts/pitch_angles.py` — deleted the local `0.001844` literal; the guard
     now imports `_APIFY_COST_PER_ITEM` ($0.002) from `src.monitor.tools.reddit_search`, so
     exactly one rate constant exists for this actor (ADR-0007 rule 1). Recomputed the
     `--max-posts` help-text example ($0.57 → $0.62). Corrected the stale `$0.001844` rate in
     `ApifyRedditScraper`'s docstring (`src/monitor/scraper.py`), with a note naming the
     confusion source.
- Date fixed: 2026-07-01
- Status → monitoring
- Validation evidence: 111/111 tests pass (tests/monitor + tests/generation + tests/cli), ruff
  clean on all three touched files, mypy clean on the two src files. Default Path A run now
  estimates $0.62 (was $0.57) for the same 308 items — the guard refuses anything whose TRUE
  cost exceeds $1.00 instead of anything whose under-priced estimate did. Move to closed after
  the next live Path A run's Apify billing matches the printed estimate.

### BUG-006 - TikTok scraper upsert is written in the SQLite dialect against the Postgres-only DB
- Date opened: 2026-07-01 (found by full-codebase audit, AUD-C2; independently confirmed by two
  audit passes + main-thread source read)
- Status: open
- Feature: `BaseScraper.upsert_items()` (`src/scrapers/base.py:56-101`), called unconditionally by
  `TikTokScraper.fetch_trending()` (`src/scrapers/tiktok.py:124`) — the persist step of every live
  TikTok scrape (`scripts/run_scrape.py`, `src/scrapers/recurring.py`).
- Environment: Postgres-only engine per ADR 0006 (`src/database.py` rejects any non-`postgresql`
  DATABASE_URL at import).
- Error/behavior: `base.py:15` imports `from sqlalchemy.dialects.sqlite import insert as
  sqlite_insert` and `base.py:88-91` builds the upsert with it. A SQLite-dialect
  `OnConflictDoUpdate` construct cannot compile against a Postgres engine — the first
  `upsert_items()` call in a real run raises a SQLAlchemy compilation error. The path is currently
  dormant (the 72K archive came in via `scripts/ingest_archive.py`, which bypasses this), so no
  live failure has been observed yet — but any future rescrape (P4 data refresh) hits it
  immediately. Two adjacent latent bugs in the same path: `tiktok.py:111-112` returns a bare `[]`
  where the signature promises a 3-tuple (callers unpack → `ValueError`), and `collected_at` is
  promised as conflict-updated by the `base.py:61` docstring but missing from `mutable_fields`
  (`base.py:74`), so freshness timestamps would never update even after the dialect fix.
- Reproduction steps:
  1. `uv run python scripts/run_scrape.py --niche <any> --limit 2` against the real Postgres DB
     with a valid `APIFY_API_TOKEN` (or stub `_normalize_item` items and call
     `TikTokScraper(db).upsert_items(items)` directly against the Postgres engine — no Apify spend
     needed to reproduce; the compile error fires before any row lands).
  2. Observe the SQLAlchemy dialect/compile error on the `ON CONFLICT` statement.
- Root cause: the upsert was written in the P0/P1 SQLite era and never migrated when ADR 0006
  removed the SQLite backend. It stayed invisible because `tests/scrapers/test_tiktok_scraper_upsert.py:19`
  runs on `sqlite:///:memory:` — the exact dialect the code hardcodes — a systemic test-fixture
  gap (audit AUD-H13f: 14 test files use in-memory SQLite against a Postgres-only app).
- Attempted fixes:
  1. None yet. Fix direction (audit AUD-C2): switch to `sqlalchemy.dialects.postgresql.insert`
     (the correct pattern already exists in `src/rag/indexer.py`); add `"collected_at"` to
     `mutable_fields`; fix the `[]` early return to `([], 0, 0)`; and cover the path with a
     Postgres-dialect test (real container on :5433) rather than in-memory SQLite.


### BUG-008 - Context agent retrieved zero on-topic reactions: hub-sub scoping x scoped "top" sort
- Date opened: 2026-07-02 (found by first Task 8 Step 2 live --topic run: "Wistoria Episode 11,
  Elfie lost Will to Zeo")
- Status: fixed (live-probe validated same day)
- Feature: `ContextAgent._lookup_community` (`src/monitor/context_agent.py`) +
  `reddit_search` scoped sort (`src/monitor/tools/reddit_search.py`) — the retrieval front-end
  of the Path B pitch pipeline.
- Environment: live Apify `harshmaur/reddit-scraper` runs, $1.15 spent, 5 searches, 525 items.
- Error/behavior: all 5 reddit searches returned all-time r/anime megathreads (Chainsaw Man Ep 1
  x3, Made in Abyss Ep 13, Spy x Family Ep 1), zero Wistoria content. Gap agent had no relevant
  evidence; idea-fit gate correctly killed the event (cheap_meme / heat=0.10). Agent burned its
  retry budget rephrasing the query — the failing variables (sort/time) are not agent-visible.
- Root cause: TWO-LAYER INTERACTION, neither wrong alone.
  (1) `_lookup_community` took the FIRST reddit URL from one Tavily search -> r/anime (defensible:
  r/anime hosts episode megathreads), never considering the dedicated r/Wistoria.
  (2) scoped `searchSort="top"` + no time window: term matching is token-loose and all-time
  upvote ranking buries any niche thread below maxPostsCount=5 in a 10M-member sub. The 07-01
  probe that validated top+scoped ran against tiny r/Wistoria — a dedicated-sub regime where
  everything matches; the conclusion overgeneralized (BUG-004 kin: probe regimes matter).
- Attempted fixes:
  1. FIXED (commit pending this entry): (a) `reddit_search` now pins `searchSort="relevance"` +
     `searchTime="month"` always (conditional deleted; upvote-consensus signal is unaffected —
     it lives in crawled comments, not post-discovery ranking); (b) `_lookup_community` collects
     ALL subreddit candidates and prefers one whose name matches a topic token (Wistoria ->
     r/Wistoria), falling back to first-candidate. Validation: unit tests (regression tests for
     both layers) + one $0.23 live probe: same query family, same r/anime scope, new params ->
     4/5 posts were Wistoria S2 threads including the exact "Episode 11 discussion" target.
