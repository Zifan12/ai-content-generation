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

### BUG-009 - Context-agent reaction_sample keeps search-relevance order + hard-truncates to 2000 chars, burying the high-upvote signal
- Date opened: 2026-07-03 (found analyzing the first fully-completed Task 8 tail run, event #7)
- Status: open (fix in progress, user-written)
- Feature: `ContextAgent.gather` truncation (`src/monitor/context_agent.py:428-431`, the
  `reaction = reaction[:2000]` slice) fed by the block-assembly order in `reddit_search`
  (`src/monitor/tools/reddit_search.py` — posts are emitted in the Apify actor's
  relevance order, never re-ranked). **Path B (`--topic`) only.** Path A already ranks:
  `ApifyRedditScraper._pick_reaction_comments` sorts by `commentUpVotes` desc
  (`src/monitor/scraper.py:310`); Path B's context-agent path never got that treatment.
- Environment: live `--topic` run, OpenRouter fleet, Postgres event #7
  ("Wistoria fans imagining what if Elfie won Will instead of Zeo after episode 11").
- Error/behavior: `reaction_sample` is built by concatenating each `reddit_search` text blob
  (posts in relevance order) into `state.reddit_text`, then hard-slicing the first 2000 chars in
  `gather()`. No upvote ranking anywhere on Path B. On event #7 the stored `reaction_sample`
  (length exactly 2000, ends mid-word) LED with a **15-upvote** joke thread ("Trebuchet / Fortnite
  battle bus / Assassinate Kreutz") and **truncated away** the **244-upvote** sincere thread
  ("This episode was so wholesome and peak Wistoria, Will & Elfie are just meant to be"). The gap
  agent, reading a meme-skewed sample, produced `dominant_emotion="playful longing"` and
  `audience_want`= the absurd-tools framing; 2 of 3 resulting pitches were meme-flavored (trebuchet
  launch, permit-paperwork satire). NOT a pitcher or craft-gate defect — the craft gate passed all
  three on craft (`clear_desire`/`visible_turn`/`earned_payoff`/`emotion_physical_tell` all true);
  both stages did their jobs on garbage-skewed input. The `--force`d idea-fit gate had itself
  flagged this topic `cheap_meme` — its instinct was right about the meme skew.
- Reproduction steps:
  1. Run `uv run python -m scripts.pitch_angles --topic "<topic mixing a loud low-upvote joke
     thread with a quieter high-upvote sincere thread>" --force`.
  2. Dump `event.reaction_sample` from Postgres (latest `TrendingEventRecord`).
  3. Observe: order is relevance, not upvotes; length capped at 2000; the high-upvote thread is
     cut off while a low-upvote thread survives.
- Root cause: truncation is applied to an UNRANKED string, so "which 2000 chars survive" is decided
  by relevance-of-post-discovery, not by crowd consensus (upvotes) — even though upvotes are the
  pipeline's designated "how many humans co-signed this" signal (see BUG-008 / the upvote-tagging
  work). Same single-source-of-truth spirit as BUG-005: Path A ranks by upvotes, Path B silently
  does not.
- Attempted fixes:
  1. (2026-07-03) FIXED (code) in `reddit_search` — Option A, rank where posts are still
     structured dicts, not after flattening to a string. Added `_upvotes(item, fallback_field)`
     (mirrors `_tag`'s `score`→fallback priority, coerces to int, missing→0 per the
     `_comment_upvotes` convention in `scraper.py`); the post loop now builds one
     `(upvotes, block, url)` bundle per post and `ranked.sort(key=..., reverse=True)` orders them
     highest-upvote-first before the join (stable sort → ties keep relevance order). `urls` is
     rebuilt from the sorted bundles, still skipping None. KNOWN LIMITATION recorded in-code: this
     ranks WITHIN one `reddit_search` call; across-call ordering (the `_act_reddit` string
     concatenation) is not handled — that needs a structured-accumulation change and is deferred.
- Date fixed: 2026-07-03 (code); live-validation pending.
- Validation evidence: offline GREEN — `tests/monitor` 104 passed / 1 skipped, ruff clean on the
  file, mypy adds 0 new errors (only the pre-existing tavily stub error remains). LIVE pending —
  re-run event #7's topic and confirm the 244-upvote thread now leads the sample and the
  gap/pitches shift from "playful/meme" to sincere.
- Follow-up (2026-07-08): the "across-call ordering... deferred" limitation above is still open
  and still un-ticketed on its own. Re-examined while live-testing the same-day targeted-grounding
  fix (see BUG-023's `unresolved_facts` mechanism): if the planner calls `reddit_search` twice in
  one run, call #2's text is appended after call #1's in `state.reddit_text`
  (`context_agent.py:350`), and `gather()`'s final `_truncate_to_whole_blocks` cut is applied to
  that concatenation as a whole — call #2 can be silently starved by a long call #1 regardless of
  its own upvotes, since ranking only happens within each call, never across the merge.
  Narrower in practice than it first looked, though: `PLAN_SYSTEM_PROMPT` (lines 78-83) routes
  fact-resolution to `tavily_search`, not a second `reddit_search` — `tavily_text` is a separate
  accumulator that never enters the 2000-char-capped `reaction_sample` at all, and `_finalize`
  (which produces `summary`/`key_moments`/`unresolved_facts`) reads the full untruncated
  `reddit_text` + `tavily_text` before any truncation runs. So the risk is real only when the
  planner issues a second `reddit_search` for more reaction color, not when it's resolving an
  unclear fact — confirmed by re-reading `context_agent.py` end to end, not by inference.
  Checked second-brain (Chip Huyen, `raw/ai-engineering-ch06-rag-and-agents.txt`): this matches
  the documented "combining retrieval algorithms" pattern (reciprocal rank fusion / recency-
  weighted reranking — merge-then-truncate, not concatenate-then-truncate); the FIFO critique
  there ("order-based retention assumes early content matters least, an assumption that can be
  badly wrong") names this exact failure shape. Not a stretch-fit — direct match, high confidence.
  Fix: not attempted — still deferred, now with a concrete direction (recency-weighted rerank
  across accumulated `reddit_search` calls before the char-budget cut) if picked up.
- Note (2026-07-08, context-agent-grounding-hardening plan): this entry's fix surfaced a follow-on
  cost/signal-quality issue — the reddit_search fetch params over-fetch ~5x what survives the
  2000-char truncation this entry also introduced, paying Apify for text that's fetched then
  discarded, some of it low-signal. Tracked and fixed separately as BUG-024 (fetch-size halved,
  commit `cfe94b3`; sub-5-upvote comment noise floor added, commit `5636335`; both 2026-07-08). This
  entry's own remaining KNOWN LIMITATION — upvote ranking works WITHIN one `reddit_search` call but
  not ACROSS the multiple accumulated calls `_act_reddit` makes — is a structured-accumulation
  change and was explicitly NOT part of that plan. Status stays open for that reason.

### BUG-010 - Langfuse records no token/cost/model for OpenRouter-seat generations — cost & near-truncation auditing is blind since the fleet migration (BUG-001 regressed for the new provider)
- Date opened: 2026-07-03 (found doing a per-call Langfuse health audit of the Task 8 tail run)
- Status: fixed (code applied + offline green; live-trace confirmation pending)
- Feature: `src/providers/llm/openrouter_llm.py` `parse_with_raw` (the `@traced("openrouter_llm.parse")`
  span). Affects ALL 7 LLM seats now that the fleet routes through OpenRouter (commit `0dece0b` +
  the seat migration `780bb6e`/`d4da985`/`320da0b`).
- Environment: Langfuse US cloud (live); observations pulled via the public REST API
  `GET /api/public/observations?type=GENERATION`.
- Error/behavior: across 100 recent `openrouter_llm.parse` GENERATION observations, `promptTokens`,
  `completionTokens`, `totalTokens`, `calculatedTotalCost`, and `model` all come back **null / 0**.
  The `level`/`statusMessage`, `input`, `output`, and `latency` fields ARE populated (error
  detection still works — the audit correctly surfaced the two known truncation ERRORs and nothing
  else). Contrast BUG-001 (closed 2026-06-14): `anthropic_llm.parse` generations DO carry
  `usage_input_tokens` / `usage_output_tokens`. So the token/cost observability BUG-001 restored is
  ABSENT for the new provider — a blind spot introduced by the OpenRouter migration. Consequence:
  a per-call audit cannot see output sizes (the exact signal that would flag a seat sitting near
  its `max_tokens` — i.e. the next StoryCraftVerdict/StoryPitchSlate-class truncation before it
  crashes) nor per-seat cost, straight from Langfuse.
- Reproduction steps:
  1. Run any pipeline that exercises the OpenRouter seats (all of them now).
  2. `GET {LANGFUSE_HOST}/api/public/observations?type=GENERATION` with the pk/sk as basic auth.
  3. Observe `promptTokens`/`completionTokens`/`calculatedTotalCost`/`model` null on every
     `openrouter_llm.parse` observation.
- Root cause: CONFIRMED at source (2026-07-03). `traced` (`src/observability/tracing.py`) just wraps
  `langfuse.observe()`, which does NOT populate token usage / model — those must be set explicitly on
  the observation. NEITHER wrapper did so: `parse_with_raw` computes the counts into `raw` but only
  `logger.info`s them; it never tells Langfuse. (The Anthropic path only LOOKED fine because Langfuse
  auto-recognizes the Anthropic SDK client; the openai-SDK-over-OpenRouter transport is not
  auto-instrumented, so its generations show null.) Two adjacent tracing defects surfaced in the same
  read: (a) `IdeaFitGate.evaluate` had NO `@traced` span at all — its LLM call showed only as a
  parentless `openrouter_llm.parse` generation; (b) `@traced(capture_input=True)` auto-captured the
  `response_model` positional arg — a Pydantic CLASS — which serialized to `<mappingproxy>` /
  `<member_descriptor>` garbage in every generation's input.
- Attempted fixes:
  1. (2026-07-03) In BOTH `parse_with_raw` wrappers (anthropic + openrouter), set the `@traced`
     decorator `capture_input=False, capture_output=False` and add one
     `get_client().update_current_generation(input={system,prompt,schema}, output=..., model=self.model,
     usage_details={input, output})` call — fixes the null usage/model AND the `<mappingproxy>` input
     together. Also decorated `IdeaFitGate.evaluate` with `@traced(name="idea_fit_evaluate")` (mirrors
     the other stage spans) so the gate finally gets a named parent span.
- Date fixed: 2026-07-03 (code applied; live-trace confirmation pending)
- Validation evidence: offline green — `tests/monitor` + `tests/providers` 127 passed / 1 skipped (the
  127 exercise `parse_with_raw` with the new `update_current_generation` call in place: returns the
  parsed model correctly, no crash); ruff clean on all 3 edited files; mypy +0 new (`anthropic_llm.py`
  holds at its 17 pre-existing Anthropic-SDK typing errors, `openrouter_llm.py` + `idea_fit_gate.py`
  clean). PENDING: a live pitch run → re-pull `/api/public/observations` and confirm populated
  `promptTokens`/`completionTokens`/`model`, a named `idea_fit_evaluate` span, and clean
  (non-`<mappingproxy>`) generation input.

### BUG-011 - StoryCraftVerdict truncated at the shared max_tokens=1024 default — crashed the first fully-completed Task 8 tail run
- Date opened: 2026-07-02 (crashed the first live `--topic --force` tail run of the session)
- Status: closed (fixed + offline & live validated this session)
- Feature: `StoryCraftGate.evaluate` (`src/monitor/story_craft_gate.py`, the
  `self.llm.parse(response_model=StoryCraftVerdict, ...)` call) — the per-pitch craft gate, run once
  per pitch (plus one bounded repair).
- Environment: OpenRouter fleet, model `anthropic/claude-sonnet-5`, live `--topic --force` run.
- Error/behavior: `src.providers.llm.anthropic_llm.TruncatedResponseError: Response hit
  max_tokens=1024 before completing (StoryCraftVerdict, model=anthropic/claude-sonnet-5)`. The
  `evaluate()` call inherited the shared default `max_tokens` (1024); a real `StoryCraftVerdict`
  (4 pass/fail dimensions + `notes` + `failure_notes`) exceeds 1024, so the JSON truncated mid-object
  and the run died at the craft gate — AFTER gate/gap/pitcher had run (and the pitcher's own
  `e8fbfe5` `_PITCH_MAX_TOKENS` fix had just proven out for the first time). Same failure class as
  `WRITER_MAX_TOKENS` and `_PITCH_MAX_TOKENS` (see the `shared_max_tokens_truncation` learning): the
  shared 1024 default truncates a large structured output whenever a per-caller override is missing.
- Reproduction steps:
  1. Pre-fix, run the Path B tail (`pitch_angles --topic "<x>" --force`) so it reaches the craft gate
     on a real pitch.
  2. Observe `TruncatedResponseError ... max_tokens=1024 ... StoryCraftVerdict` from
     `story_craft_gate.evaluate`.
- Root cause: the craft-gate `parse()` call carried no per-caller `max_tokens` override, so it used
  the shared 1024 default — too small for the verdict schema.
- Attempted fixes:
  1. (2026-07-03, user-written) Added a per-caller `max_tokens` constant in `story_craft_gate.py`
     (mirrors `_PITCH_MAX_TOKENS` / `WRITER_MAX_TOKENS`) and passed it into the `parse()` call. Did
     NOT raise the shared default — scalpel, not shotgun — so the small classification seats keep
     their 1024 truncation guard as an early-warning canary.
- Date fixed: 2026-07-03
- Validation evidence: offline `tests/monitor` 104 passed / 1 skipped; live
  `RUN_LIVE=1 pytest tests/monitor/test_story_craft_gate_live.py` 1 passed (a real `StoryCraftVerdict`
  parse completed via OpenRouter/Sonnet on the exact crashing path); and the subsequent
  `--topic --force` tail then ran end-to-end, producing 3 craft-passed pitches with no truncation.
  Closed.

### BUG-012 - StoryPitcher slate has low diversity: 3 near-clone pitches from one gap
- Date opened: 2026-07-03 (surfaced on the BUG-009-fixed rerun, event #8 Wistoria/Elfie)
- Status: open
- Feature: `StoryPitcher.pitch` slate generation (`src/monitor/story_pitcher.py`) — produces the
  N-pitch slate for one event; a downstream diversity check flags near-duplicate slates.
- Environment: live `--topic --force` rerun, OpenRouter fleet (pitcher seat = sonnet-via-OpenRouter).
- Error/behavior: printed `Story slate low diversity: avg pairwise cosine 0.735 >= 0.70 threshold`.
  All 3 surviving pitches were variations of ONE premise ("Zeo never intervenes → Elfie's decade of
  devotion → Will's fate"): [1] a duel, [2] a "nobody showed up" satire reveal, [3] a "Will looks
  back" reveal. Cosmetic variation, not 3 distinct concepts. The craft gate passed each one
  individually (each is well-built), so this is a SLATE-level quality gap, not a per-pitch one —
  hits any topic, not just this one. Also NOTE: the check only WARNS; the low-diversity slate still
  gets persisted and shown.
- Reproduction steps:
  1. Run any narrow-gap event through the pitcher (`pitch_angles --topic "<x>" --force`).
  2. Observe the `low diversity` warning and near-duplicate loglines in the slate.
- Root cause: SUSPECTED — the pitcher generates N pitches from a single `audience_want`/gap without
  an explicit inter-pitch diversity constraint, so a narrow gap collapses the slate onto one idea.
  To confirm: whether the pitcher prompt asks for distinct angles, and whether the diversity check
  is wired to do anything beyond print a warning.
- Attempted fixes:
  1. None yet. Direction: push the pitcher for genuinely distinct angles (vary protagonist / POV /
     structure across the slate), and/or have the diversity check trigger a re-pitch of the
     too-similar entries instead of only warning.
- Date fixed: —
- Validation evidence: pending.

### BUG-014 - `_lookup_community`'s no-dedicated-subreddit fallback silently reintroduces the exact mega-sub failure BUG-008 fixed
- Date opened: 2026-07-04 (found building Task 1's fixture set for the pitcher-groundedness-fix
  plan, `docs/superpowers/plans/2026-07-03-pitcher-groundedness-fix.md`; topic: Obsession (2025)/
  Nikki Freeman deleted ending)
- Status: open
- Feature: `ContextAgent._lookup_community` (`src/monitor/context_agent.py:190-244`) — specifically
  its "no candidate matches a topic token → fall back to `candidates[0]`" branch (line 238) — plus
  `reddit_search`'s `searchSort="relevance"` scoped search (`src/monitor/tools/reddit_search.py:181`).
- Environment: live `--topic "Obsession (2025) fans wishing the movie had kept its deleted alternate
  ending, where Nikki Freeman gets free instead of the dark fate Bear's wish trapped her in"` run,
  $0.92 Apify spend (within the $2.00 ceiling), Apify `harshmaur/reddit-scraper` actor.
- Error/behavior: the persisted `TrendingEventRecord` (id=10)'s `reaction_sample` is entirely about
  **"A Minecraft Movie" (2025)** — Steve, elytra, the End portal, Jack Black — zero connection to
  Obsession. `gap_agent`'s `audience_want` (Ender Dragon / End portal rampage) is a CORRECT read of
  the garbage it was given, not a gap_agent bug. Traced via real Langfuse observations (not
  inferred): the tool's actual call was `next_query: "Obsession 2025 deleted ending"`,
  `within_community: "r/shittymoviedetails"` — and the top-ranked result returned from that scoped,
  `searchSort="relevance"` search was an unrelated 19,512-upvote r/shittymoviedetails post about a
  different movie entirely.
- Reproduction steps:
  1. Run `--topic "<a topic with no dedicated fan subreddit>"` through Path B.
  2. Pull the real trace: `context_agent.lookup_community`'s output (the chosen `within_community`)
     and the subsequent `context_agent.act_reddit`'s output (the actual `reddit_text` returned).
  3. Observe the chosen community has no token match to the topic, and the scoped "relevance" search
     still returns an off-topic top post from that community.
- Root cause: CONFIRMED, three-layer trace, all read from current source (not the historical BUG-004/
  BUG-008 entries alone — verified the code still matches what those entries claim):
  1. `_lookup_community` (line 222) searches Tavily for `"{topic} reddit subreddit"`, extracts
     subreddit names from result URLs, and prefers one whose name token-matches the topic
     (line 239-242) — e.g. "Wistoria" → r/Wistoria. For Obsession (2025), a small recent horror
     film, no dedicated subreddit exists (or none surfaced in the URLs), so no token match — line
     238's fallback (`chosen = candidates[0]`) fires, landing on r/shittymoviedetails, Tavily's
     top-ranked hit for the generic query, unrelated to Obsession specifically.
  2. The function's OWN docstring (line 213-215) names this exactly: "when no candidate name matches
     a topic token, fall back to the first candidate, **which preserves the old behavior**" — the
     old behavior being BUG-008's original bug (first-URL-wins landed on a big generic hub, not a
     dedicated sub).
  3. `reddit_search`'s scoped `searchSort="relevance"` (fixed for BUG-008 specifically against
     r/anime, a large generic subreddit) does not actually solve "big generic subreddit + niche
     query" — it only reliably works when the community is SELF-SCOPING (small/dedicated, so
     "everything matches", per `reddit_search.py:166-167`'s own comment). r/shittymoviedetails is
     the same size/genericity class as r/anime. BUG-008's fix (token-preference + relevance sort)
     never actually eliminated the underlying mega-sub-relevance problem — it only avoids TRIGGERING
     it when a dedicated subreddit happens to exist. When none exists, the fallback path walks
     straight back into the identical failure mode, just against a different generic subreddit.
- Attempted fixes:
  1. FIXED (2026-07-04, user-written): went with direction (b) — `_lookup_community`
     (`context_agent.py:238-247`) now leaves `chosen = None` unless the token-match loop actually
     finds a match, returning `{"within_community": ""}` in that case instead of falling back to
     `candidates[0]`. Empty `within_community` routes to `reddit_search`'s unscoped
     `searchSort="relevance"` path, already validated accurate by BUG-004's own probe. Considered
     and deferred (a) (a deterministic keyword-presence floor) and a minimum-upvote guard — no
     evidence yet that either is needed; `idea_fit_gate`'s `heat_score` already exists as the layer
     that would catch a genuinely low-engagement match, and bundling untested guards violates
     one-variable-at-a-time debugging discipline. Revisit only if a real case shows the gap.
     Docstring (`context_agent.py:213-215`) and the stale regression test
     (`test_lookup_community_falls_back_to_first_candidate_when_no_token_match` →
     `test_lookup_community_empty_when_no_token_match`, `tests/monitor/test_context_agent.py`)
     updated to match.
- Date fixed: 2026-07-04
- Validation evidence: `tests/monitor/test_context_agent.py` 18/18 passing. Live re-run of the same
  Obsession topic string: `within_community` came back empty (unscoped), Apify spend dropped to
  $0.23 (vs $0.92 scoped), and the persisted `TrendingEventRecord`'s `reaction_sample` is genuine,
  on-topic Obsession discussion (2,892-upvote real post re: Bear/Nikki's fate) — confirmed by direct
  DB read, not just the console summary line. Unblocks Task 1 of the groundedness-fix plan.

### BUG-013 - GapAnalysis truncated at the shared max_tokens=1024 default — killed the first Task 1 fixture-building Path B run (AOT topic)
- Date opened: 2026-07-03 (crashed the first real `--topic` run made while building the pitcher-groundedness-fix fixture set, `docs/superpowers/plans/2026-07-03-pitcher-groundedness-fix.md` Task 1)
- Status: open
- Feature: `GapAgent.analyze` (`src/monitor/gap_agent.py`, the `self.llm.parse(response_model=GapAnalysis, ...)` call) — runs once per surviving event, before the pitcher.
- Environment: OpenRouter fleet, model `deepseek/deepseek-v4-pro`, live `--topic "Attack on Titan fans reacting to the series finale backlash"` run (no `--dry-run`; real Apify+LLM spend, $0.92 of the $2.00 context-agent ceiling already spent when it crashed).
- Error/behavior: `src.providers.llm.anthropic_llm.TruncatedResponseError: Response hit max_tokens=1024 before completing (GapAnalysis, model=deepseek/deepseek-v4-pro)`. Same failure class as `WRITER_MAX_TOKENS` / `_PITCH_MAX_TOKENS` / BUG-011's `StoryCraftVerdict` fix (the `shared_max_tokens_truncation` learning): `analyze()`'s `parse()` call carries no per-caller `max_tokens` override, so it falls back to the shared 1024 default. Did not trip on the earlier Wistoria runs (events 7/8) — truncation is output-length-dependent, and AOT's real GapAnalysis (dominant_emotion, audience_want, evidence_quotes, reasoning) apparently ran long enough to exceed 1024 where Wistoria's happened not to. `gap_agent.py` is the one pipeline seat in this family (`story_pitcher.py` has `_PITCH_MAX_TOKENS=8192`, `story_craft_gate.py` fixed in BUG-011) that never got the per-caller override.
- Reproduction steps:
  1. Run `uv run python -m scripts.pitch_angles --topic "<a topic whose real GapAnalysis output runs long>"`.
  2. Observe `TruncatedResponseError ... max_tokens=1024 ... GapAnalysis` from `gap_agent.analyze`.
- Root cause: `gap_agent.py`'s `analyze()` `parse()` call has no per-caller `max_tokens` argument — uses the shared 1024 default, same class as BUG-011.
- Attempted fixes:
  1. None yet. Direction (mirrors BUG-011's fix exactly): add a per-caller `max_tokens` constant in `gap_agent.py` (e.g. `_GAP_MAX_TOKENS`, matching `_PITCH_MAX_TOKENS`'s 8192) and pass it into the `parse()` call. Do not raise the shared default.
- Date fixed: —
- Validation evidence: pending — blocks Task 1 of the groundedness-fix plan until fixed (can't pull a real `GapAnalysis` for any topic whose output happens to run long).

### BUG-011 - executor uniform argv incompatible with minimax_hailuo CLI contract
- Date opened: 2026-07-05
- Status: monitoring (workaround shipped; real fix pending)
- Feature: render executor (`src/generation/executor.py` `_cost_argv`/`_create_argv`), first hit during pitch-29 real-render preflight
- Environment: Higgsfield CLI 1.1.5, Windows
- Error/behavior: `higgsfield generate cost minimax_hailuo --prompt ... --aspect_ratio 9:16 --duration 4` exits 4:
  "Invalid values: duration=4 (allowed: 6,10)" + "Unknown params: aspect_ratio". The executor builds ONE argv
  shape for every video model; hailuo's contract differs (duration 6|10 only, no aspect_ratio param, wants
  resolution 512|768|1080 + variant; `hf model get minimax_hailuo`). Task-6 CLI verification covered
  kling3_0/veo3_1/nano_banana_2, never hailuo. Any 4-5s shot tagged fluid_motion/impossible_physics crashed
  the whole preflight (writer nondeterminism means this fires intermittently across runs of the SAME pitch).
- Reproduction steps:
1. Run the smoke script --real on any pitch until the writer tags a shot fluid_motion or impossible_physics
   with duration not in {6,10} (pitch 29 run 2026-07-05 19:13 did).
2. Preflight cost loop raises CalledProcessError exit 4 before any spend.
- Attempted fixes:
1. (2026-07-05) Workaround: pulled minimax_hailuo from `routing:` keys in config/render_rules.yaml
   (impossible_physics, fluid_motion) with a dated BUG-011 comment. Seedance/Veo take those tags; render
   unblocked. Hailuo model block + evidence kept.
- Root cause: executor assumes one uniform CLI param shape across video models; per-model param
  contracts (duration granularity, aspect vs resolution, variant) are not encoded in render_rules.yaml
  ratings nor consulted by the router/adapter, so incompatible (model, duration) pairs are constructible.
- Final fix: TBD — encode per-model CLI param constraints in render_rules.yaml and make routing/argv
  construction respect them (router must not route a shot to a model whose duration set excludes it).
- Validation evidence: post-workaround rerun routes 0 jobs to hailuo (pending next --real run).

### BUG-015 - HiggsfieldTTS spends credits with no estimate-before-spend (ADR-0007 violation)
- Date opened: 2026-07-05
- Status: open
- Feature: TTS narration (`src/providers/tts/higgsfield_tts.py`, called from `src/generation/assembly.py` narration stage)
- Error/behavior: `synthesize()` fires a paid `text2speech_v2` CLI call (~0.15cr/line) with no
  cost estimate, accumulation, or threshold refusal — unlike the executor's render path, which
  runs `generate cost` per job before any paid call. The smoke script's credit table covers
  render jobs only; narration spend is invisible until it happens. A many-line package or a
  retry loop spends unguarded — the exact incident class ADR-0007 rule 2 exists to prevent.
- Found by: /code-review 2026-07-05 (verified CONFIRMED)
- Design fork to resolve first: estimate inside `synthesize()` per call vs one package-level
  estimate in `assemble()` before the narration loop; and whether 0.15cr/line x line-count
  arithmetic suffices or a CLI cost quote exists for TTS jobs.
- Attempted fixes: (none — logged for later; sanitization sibling issue fixed same day)

### BUG-016 - consistency_groups() groups shots on the LLM-echoed cast the writer itself distrusts
- Date opened: 2026-07-05
- Status: open
- Feature: multi-shot render routing (`src/generation/render_adapters/router.py:126`, fed by `src/generation/content_writer.py`)
- Error/behavior: grouping keys on `frozenset(draft.characters_in_frame)` (call-1 LLM echo),
  but the final ShotSpec deliberately copies `beat.characters_in_frame` per the "trust code
  over LLM" doctrine. Nothing validates draft cast == beat cast before grouping, so a mis-echo
  (the WRONG_ECHO test fixture proves the path) can merge/split Kling shared-seed groups on a
  wrong cast while the package reports the correct one — silent wrong-face/wrong-outfit
  grounding (BUG-002 class), undetectable from the package alone.
- Found by: /code-review 2026-07-05 (verified CONFIRMED)
- Design fork to resolve first: validate-and-fail vs substitute beat cast into grouping vs
  repair-retry the draft. (Substitution matches the existing trust-code-over-LLM doctrine.)
- Attempted fixes: (none yet)

### BUG-017 - Mandatory-grounding invariant (DECISIONS_LOCKED L3) enforced nowhere in the pipeline
- Date opened: 2026-07-05
- Status: open
- Feature: render pipeline (`src/generation/render_adapters/adapter.py` ~L91, `src/generation/executor.py` `_create_argv`)
- Error/behavior: content_writer docstring defers ("the render layer owns that gate"), adapter
  forwards `list(package.reference_image_paths)` unchecked, and executor emits zero
  `--image-references` flags when the list is empty. Only guard is argparse `required=True` in
  scripts/smoke_content_writer.py. Any other caller passing `reference_image_paths=[]` renders
  completely ungrounded stills — credits burned, no error, no warning, no log line.
- Found by: /code-review 2026-07-05 (verified CONFIRMED)
- Design fork to resolve first: which layer owns the invariant — writer input validation,
  adapter, or executor (the docstring's "render layer owns it" claim may itself be the bug).
- Attempted fixes: (none yet)

### BUG-018 - executor cost preflight ignores the resume manifest — resumed runs print inflated estimates
- Date opened: 2026-07-05
- Status: open
- Feature: render executor (`src/generation/executor.py` ~L277 cost loop vs ~L293 manifest load)
- Error/behavior: `execute()` runs `generate cost` for ALL jobs and prints "Estimated total"
  BEFORE loading render_manifest.json; the completed-job skip check lives in the second loop.
  On a resume with N of M jobs completed, the printed total (and each per-job line) covers all
  M jobs, not the M-N that will actually spend. `dry_run=True` on a partial out_dir returns the
  same inflated `credits_spent`.
- Found by: /code-review 2026-07-05 (verified CONFIRMED)
- Design fork to resolve first: load manifest before the estimate and cost only pending jobs,
  vs keep the full estimate and print both totals (full vs remaining).
- Attempted fixes: (none yet)

### BUG-019 - shared max_tokens=1024 default keeps truncating structured output; interface codifies the per-caller bandaid
- Date opened: 2026-07-05
- Status: open
- Feature: LLM providers (`src/providers/llm/anthropic_llm.py` parse/parse_with_raw, `src/providers/llm/openrouter_llm.py` twins)
- Error/behavior: the 1024 default has bitten repeatedly (BUG-011 StoryCraftVerdict, BUG-013
  GapAnalysis, writer chain, context-agent finalize); six per-caller constants now exist
  (WRITER / _FINALIZE / _GAP / _PITCH / _STORY_CRAFT / _GROUNDEDNESS _MAX_TOKENS) and the
  TruncatedResponseError docstring instructs future callers to add a seventh ("the fix is
  always per-caller, never the shared default"). Every new seat inherits 1024, burns one paid
  call discovering the trap, then adds another magic number.
- Found by: /code-review 2026-07-05 (verified CONFIRMED; altitude finding)
- Design fork to resolve first: make max_tokens a required kwarg (one loud break at all call
  sites) vs raise the shared default vs derive from the response schema.
- Attempted fixes: (none — pattern documented in TruncatedResponseError docstring as policy,
  which is the thing this bug challenges)

### BUG-012 - real-human-face reference images hard-blocked as "nsfw" by Higgsfield still model
- Date opened: 2026-07-05
- Status: closed (not a code bug - provider moderation; pipeline constraint documented)
- Feature: reference grounding (L3) for live-action IP; hit on pitch-29 real render attempt 5
- Environment: Higgsfield CLI 1.1.5, nano_banana_2
- Error/behavior: `generate create nano_banana_2 --image-references <real actress frames>` ends
  status "nsfw" (exit 3), credits auto-refunded. Three-way isolation 2026-07-05: gore prompt +
  refs = nsfw; gore-free prompt + refs = nsfw; same prompt no refs = renders. Trigger = the
  photographic human-face references, not prompt text. Matches video_model_system_guide.md L440
  "Human reference suspended (Feb 2026)" - live and enforced server-side on Higgsfield.
- Root cause: provider moderation policy on photographic face references.
- Resolution: constraint accepted. Live-action/real-actor pitches CANNOT be reference-grounded
  on this stack -> render only drawn/rendered fictional-character IP (anime/game key art passes;
  evie render proved it). No filter-evasion workarounds (out of policy). The 2026-06-27 spec's
  real-actor-likeness deferral is now provider-enforced, not just a design choice.
- Validation evidence: transactions show spend+refund pairs for both blocked jobs; no-refs
  control rendered a valid PNG (job 26722f9d, 2026-07-06 01:54).

### BUG-020 - assembly concat.txt writes CWD-relative paths; ffmpeg concat demuxer doubles them and crashes
- Date opened: 2026-07-05
- Status: open
- Feature: video assembly (`src/generation/assembly.py` ~L146 concat step; concat.txt writer upstream)
- Error/behavior: on the pitch-24 real render, all 6 renders + 5 clips succeeded (~80cr spent) but
  the final `assemble()` crashed at the `-f concat -safe 0 -i concat.txt -c copy` step with
  `CalledProcessError` exit 4294967294 (-2). concat.txt lives in `<out_dir>/_assembly/` but its
  `file '...'` lines carry the full repo-relative path `output/smoke_runs/.../\_assembly/norm_N.mp4`.
  The concat demuxer resolves each `file` path RELATIVE TO concat.txt's own directory, so ffmpeg
  tries `_assembly/output/smoke_runs/.../\_assembly/norm_0.mp4` (doubled) → "No such file or directory".
  norm_*.mp4 exist and are valid (uniform 1080x1920 h264); only the path reference is wrong. Manual
  concat with BARE filenames (`file 'norm_0.mp4'`) from inside _assembly stitched all 5 into a valid
  25.3s mp4 — proving the renders are fine and only the concat.txt path form is the bug.
- Found by: pitch-24 manual render 2026-07-05 (salvaged to _assembly/pitch24_salvage.mp4)
- Design fork to resolve first: write concat.txt entries as bare basenames (they already sit beside
  concat.txt) vs write absolute paths vs run ffmpeg with cwd set to _assembly. Basename is simplest
  and matches how the demuxer resolves.
- Attempted fixes: manual salvage concat only (bare filenames) — root writer not yet changed.
- FIXED 2026-07-07: concat.txt entries now `Path(p).resolve().as_posix()` (absolute — chosen over
  basename so the fix also holds if norm files ever move out of _assembly; -safe 0 already set).
  Verified live on the first motion-native assembly (pitch-24 take_1 -> final.mp4, 15.1s).
- Status: FIXED

### BUG-021 - anchors_block is a global all-character block prepended to EVERY still; forces the whole cast into solo shots
- Date opened: 2026-07-05
- Status: open
- Feature: writer + render adapter (`src/generation/content_writer.py` anchors_block authoring, `src/generation/render_adapters/adapter.py` L46 `parts = [package.anchors_block, shot.still_prompt, package.style_anchor]`)
- Error/behavior: pitch-24 shot 0 (hook) should show ONLY young Elfie + a plush. The rendered still
  crammed all three adults (Will, Elfie, Zeo) into the background behind the child. Cause: anchors_block
  is one package-level string naming every character, and adapter L46 prepends it verbatim to EVERY
  still prompt — so a beat whose `characters_in_frame` is a subset still gets the full cast forced in.
  Identity text should be scoped to each shot's actual `characters_in_frame`, not global.
- Found by: pitch-24 render eyeball 2026-07-05
- Design fork to resolve first: per-shot anchors composed from the beat's characters_in_frame (kills the
  bleed AND is the natural home for the BUG-class fix below) vs keep global block. Ties into the planned
  vision-describe fix — anchors should be (a) per-shot cast and (b) code-set from ref-derived appearance
  descriptions, not LLM-invented (the blind writer swapped Will/Zeo hair on pitch 24; hand-patched for
  that render only via a pitch_id==24 override in scripts/smoke_content_writer.py — remove when real fix lands).
- Attempted fixes: (none — pitch-24 used a temporary hardcoded anchors override, not a real fix)
- FIXED 2026-07-14: neither design fork above was taken — a third option won. anchors_block is deleted
  ENTIRELY (schema, writer, adapter), so there is no more per-shot-vs-global question: the prompt never
  describes appearance at all, key-art alone carries it, and the adapter composes only positional ref
  bindings ("X is the character shown in imageN"). The pitch_id==24 hardcoded override this entry
  references is also removed (scripts/smoke_content_writer.py). Note: the still-lane this entry's
  Feature/Found-by lines describe (per-shot stills, adapter L46 `parts=[...]`) was already retired
  2026-07-07 by the motion-native scene-lane rewrite, before this fix — this FIXED note applies to the
  CURRENT scene-lane adapter's `_identity_block`, which inherited the same global-anchors defect.
- Status: FIXED

### BUG-022 - StoryPitch mode="other" would KeyError the craft gate (unguarded playbook lookup)
- Date opened: 2026-07-07 (surfaced tracing the `mode` field after demoting the idea-fit gate's payoff check)
- Status: open (parked — low-probability, pre-existing; logged not fixed)
- Feature: `StoryCraftGate.evaluate` (`src/monitor/story_craft_gate.py:107`, the bare
  `self.playbook[pitch.mode.value].craft_emphasis` index), fed by `StoryPitcher` which sets
  `StoryPitch.mode`.
- Environment: any pipeline run that reaches the craft gate; not provider-specific.
- Error/behavior: the mode playbook (`config/mode_playbook.yaml`) defines exactly two keys —
  `wish` and `satire`. `evaluate` indexes it with a bare `self.playbook[pitch.mode.value]`.
  `ContentMode` also permits `other`, and `StoryPitch.mode` has NO validator restricting it to
  playbook modes — so a pitch with `mode=other` raises an unhandled `KeyError` mid-judging (a
  crash, not a graceful skip). NOT reachable via the idea-fit gate's mode: the gate's
  `IdeaFitResult.mode` is a separate object never passed to the pitcher (`run_pitch_pipeline`
  calls `story_pitcher.pitch(event, gap, bundle)`; `GapAnalysis` carries no mode). The only
  trigger is the pitcher itself emitting `other`.
- Why low-probability: the pitcher prompt (`story_pitcher.py:154`) instructs "Each pitch commits
  to ONE playbook mode" and only wish/satire are injected, so `other` is off-instruction. But
  nothing in code prevents it — structured output would accept an off-instruction `other` and it
  crashes downstream.
- Pre-existing: independent of the 2026-07-07 idea-fit-gate payoff-check removal (that change
  touched neither the pitcher's mode choice nor this lookup). Surfaced — not caused — while
  tracing `mode` after that change.
- Reproduction steps:
  1. Construct a `StoryPitch` with `mode=ContentMode.other` (a unit test, or an LLM that ignores
     the prompt).
  2. Call `StoryCraftGate.evaluate(pitch, event, gap)`.
  3. Observe `KeyError: 'other'` at `story_craft_gate.py:107`.
- Root cause: unguarded dict index on a lookup table that defines only `wish`/`satire`, against a
  `mode` field whose type permits `other`.
- Design fork to resolve first: (a) validate `StoryPitch.mode ∈ {wish, satire}` at the schema
  (fail at parse, closest to source); (b) `.get(mode)` with an explicit reject/fallback in the
  craft gate (fail gracefully at the lookup); (c) add an `other` playbook entry (papers over — no
  real "other" content pattern exists). Not yet chosen.
- Attempted fixes: none (parked 2026-07-07 — logged, low priority).


### BUG-023 - context_agent's planner has no memory of its own past search queries, repeats them verbatim
- Date opened: 2026-07-07 (found tracing why event 8's gathered reaction was ~2/3 duplicate content)
- Status: fixed 2026-07-07
- Feature: `ContextAgent._plan` (`src/monitor/context_agent.py`), the LangGraph plan node that
  decides each loop turn whether to call `reddit_search`/`tavily_search` again.
- Environment: any Path B (`--topic`) run where the planner searches more than once.
- Error/behavior: `_plan`'s prompt told the LLM only a call *count* ("Reddit searched N time(s)"),
  never the actual past query strings. Confirmed via a live Langfuse trace (event 8, run_at
  2026-07-03 07:20:49 UTC): the planner issued `"Wistoria Elfie Zeo Will episode 11"` as the
  `reddit_search` query on calls 1 AND 2 — the exact same string, not a rephrasing — then a
  near-identical third call. Each call was an honest, correct Apify search; the duplication was
  the planner re-asking a question it had no way to know it had already asked. Net effect: the
  accumulated `reaction_sample` was ~2/3 duplicate text before the downstream 2000-char truncation
  even ran, and `gap_agent` built `audience_want` off a noisy, redundant sample.
- Root cause: `ContextAgentState` tracked call counts but never the query strings themselves, so
  `_plan`'s prompt had no way to show the model its own search history.
- Fix: added `reddit_queries`/`tavily_queries: list[str]` fields to `ContextAgentState`, appended
  to on each `_act_reddit`/`_act_tavily` call (mirroring the existing `urls` accumulation), and
  `_plan`'s prompt now renders the actual past-query lists instead of a bare count.
  `PLAN_SYSTEM_PROMPT` explicitly instructs the model not to repeat, or trivially reword, a query
  already in that list. Regression test: `test_plan_returns_llm_decision` asserts a seeded past
  query string appears in the rendered prompt.
- Follow-up fix (same day): `gather()`'s final truncation was also a blind `text[:2000]`
  character slice, cutting mid-sentence. Replaced with `_truncate_to_whole_blocks` — splits on
  the `"\n\n"` block separator (each block already ranked highest-upvoted first by
  `reddit_search`) and keeps whole blocks up to the budget, never slicing into one. Falls back to
  a hard slice only if a single block alone exceeds the budget. The 2000-char budget itself is
  unchanged — traced to commit `aa4f56d` (2026-06-30), an undocumented guess never revisited, and
  inconsistent with Path A's comment-count-based cap (`scraper.py`'s `top_comments_in_sample`) —
  not fixed here, only how the cut is made.
- Related, not fixed here: the accumulated text still had no dedup-by-post-identity safety net,
  in case two *different* queries legitimately return overlapping posts (this fix only prevents
  the planner from *asking* a redundant query; a same-query race or genuinely distinct queries
  that happen to surface the same thread would still duplicate it). Flagged separately, not yet
  fixed.


### BUG-024 - reddit_search over-fetches ~5x what survives the 2000-char budget, paying Apify for discarded content
- Date opened: 2026-07-07 (found while reviewing BUG-023's truncation fix)
- Status: fixed (code applied + offline-validated 2026-07-08; live end-to-end confirmation pending,
  see the context-agent-grounding-hardening plan's post-implementation note)
- Feature: the `reddit_search` call params `ContextAgent._act_reddit` uses
  (`_REDDIT_MAX_POSTS=5`, `_REDDIT_MAX_COMMENTS_PER_POST=20`, `_REDDIT_MAX_COMMENTS_COUNT=10` in
  `src/monitor/context_agent.py`), feeding into `gather()`'s `_REACTION_SAMPLE_MAX_CHARS=2000` cap.
- Error/behavior: one `reddit_search` call at current settings requests up to
  `5 * (1 + 20) + 10 = 115` billed items (`estimate_cost`'s own formula, `reddit_search.py:47`) —
  at $0.002/item, ~$0.23/call. Apify bills every returned item whether or not its text survives
  the later cut. Event 8's real (post-dedup) gathered text was ~10,000 characters — roughly 5x
  the 2000-char budget that actually reaches the LLM. The rest is fetched, paid for, and thrown
  away by `_truncate_to_whole_blocks`.
- Root cause: the fetch-size constants and the final char budget were never sized relative to
  each other — 2000 chars was set once (commit `aa4f56d`, undocumented, see BUG-023) and the
  fetch params separately, with no attempt to keep them in a sane ratio.
- Not a pure waste, though: `reddit_search` ranks everything it fetches by upvotes and keeps the
  highest first — some over-fetch is legitimate (gives the ranking step real candidates to choose
  from instead of locking in whatever the first few items happen to be). The question is the
  RATIO, not whether to over-fetch at all.
- Checked second-brain (Huyen's RAG chapter, `raw/ai-engineering-ch06-rag-and-agents.txt`) for a
  documented fetch:keep ratio guideline — none exists. The corpus names the general
  fetch-wide-then-rerank pattern but is explicit that retrieval-k sizing is "experiment, no
  universal formula" (`:118`, `:277`), and its truncation-cost discussion is scoped to
  model-context/token cost, never per-item billed API cost. Confirmed absence, not a gap in
  searching.
- Fix: not attempted — explicit decision (2026-07-07) to log and park rather than tune now.
  Whoever picks this up next needs to choose a fetch:keep ratio empirically (no formula to defer
  to) for `_REDDIT_MAX_POSTS`/`_REDDIT_MAX_COMMENTS_PER_POST`/`_REDDIT_MAX_COMMENTS_COUNT`.
- Attempted fixes:
  1. (2026-07-08, commit `cfe94b3`) Halved the single biggest cost driver:
     `_REDDIT_MAX_COMMENTS_PER_POST` in `src/monitor/context_agent.py` 20 -> 10
     (`5 * (1+20) + 10 = 115` items/call -> `5 * (1+10) + 10 = 65`, ~43% cheaper). A reasoned
     conservative first cut, not an empirically-derived ratio — no fetch:keep formula exists (see
     the second-brain check above), so this is a deliberate under-correction, not a claim the
     ratio is now "right".
  2. (2026-07-08, commit `5636335`) Added a comment noise floor (spec D7) in
     `src/monitor/tools/reddit_search.py`: comments scoring under 5 upvotes are dropped before
     they are ever formatted into a post's block, so they never consume `_REACTION_SAMPLE_MAX_CHARS`
     budget on low-signal text. Live-tested against real event-8 data — the thread's two most
     factually load-bearing comments survived (37, 42 upvotes) alongside redundant near-duplicate
     signal at 1-2 upvotes; the floor did not blind detection for that event. Addresses the "keep"
     side of the ratio (raising signal density of what survives truncation), complementing fix #1's
     "fetch" side (lowering what's paid for and discarded).
- Date fixed: 2026-07-08
- Validation evidence: offline GREEN on both commits — fix #1: `tests/monitor/test_context_agent.py`
  30 passed (constant is read dynamically by the test helpers, not hardcoded, so no test edits were
  needed), ruff/mypy +0 new. fix #2: `tests/monitor/test_reddit_search.py` (2 new tests) RED->GREEN,
  full `tests/monitor/` 144 passed / 1 skipped, ruff clean, mypy +0 new. LIVE PENDING: neither fix has
  been confirmed against a real Apify run yet (see the plan's post-implementation note — a full-chain
  live re-test of event 8 was deferred to after all 7 tasks land, to bound cost per this project's
  cost-governance convention rather than spend per-task).
- Scope note: this fix addresses the fetch-size and noise-floor pieces only. It does NOT touch
  BUG-009's own still-open KNOWN LIMITATION (upvote ranking works WITHIN one `reddit_search` call but
  not ACROSS multiple accumulated calls in `_act_reddit`) — that needs a structured-accumulation
  change and was explicitly out of scope for this plan. See the note appended to BUG-009.


### BUG-025 - tavily_search's snippet-only mode can't read structured wiki infobox fields, producing false unresolved_facts flags
- Date opened: 2026-07-08 (found live-testing the same-day targeted-grounding fix's
  `unresolved_facts` mechanism, see BUG-023)
- Status: open
- Feature: `tavily_search` (`src/monitor/tools/tavily_search.py`) — the tool `ContextAgent`'s
  planner calls to resolve a fact it can't confirm from the Reddit reaction alone, feeding
  `_finalize`'s `unresolved_facts` field (`ContextSynthesis`).
- Error/behavior: live-tested the retargeted planner on event 8's topic. The reaction thread
  contained a live, contested character-stat claim (a Fandom-wiki-documented fact). Tavily's
  search correctly found and returned the character's own Fandom wiki page as a reference URL,
  but `_finalize` still flagged the stat as unresolved — even though that exact page states it
  explicitly, in a structured right-hand infobox widget. Confirmed directly: fetching the same
  URL via `firecrawl_scrape` (`formats: ["markdown"]`, `onlyMainContent: true`) also omitted the
  infobox entirely; a full-page screenshot of the same URL showed the field plainly. Confirmed
  this is a known behavior class (not tool-specific): Fandom/Wikia infoboxes are commonly
  filtered out by markdown/snippet extraction as boilerplate/navigation — Firecrawl's own fix is
  `onlyMainContent: false` or `formats: ["html"]`.
- Root cause: `tavily_search()` (`tavily_search.py:55`) only calls Tavily's `.search()` endpoint,
  which returns short prose snippets around matched query terms — by design, per the tool's own
  docstring (picked over Firecrawl specifically so the agent reasons over raw snippets itself,
  not a synthesized answer). It never fetches full page content, so it structurally cannot see a
  page's infobox/sidebar fields no matter how the search query is targeted.
- Not a dead end: the correct page IS being found — its URL was already in `bundle.references`.
  The gap is purely in what `tavily_search` extracts FROM a found page, not in locating the page.
- Fix (2026-07-08, context-agent-grounding-hardening plan): implemented via a new
  `src/monitor/tools/firecrawl_extract.py` tool + `firecrawl_extract` planner action
  (`context_agent.py`), targeting Fandom's `aside.portable-infobox` element specifically rather
  than disabling content filtering entirely — see the spec
  (`docs/superpowers/specs/2026-07-08-context-agent-grounding-hardening-design.md`, D1/D9) for the
  live-verified detail. Status left "open" above reflects this entry's original diagnosis; the fix
  itself is tracked and closed in that plan's own commits, not by editing this entry's Status line
  retroactively.


### BUG-026 - context_agent's planner had no way to detect exhausted/repetitive reddit_search results, looped 16x on one topic
- Date opened: 2026-07-08 (live-tested the BUG-025 fix again on event 8's exact topic)
- Status: fixed 2026-07-08 (commit 0087078)
- Feature: `ContextAgent`'s plan/act loop (`src/monitor/context_agent.py`) — the planner LLM
  decides each turn whether to call reddit_search/tavily_search/firecrawl_extract or stop.
- Error/behavior: live run on a real, small/niche subreddit (r/Wistoria) — the planner called
  reddit_search 16 times, each with a differently-worded query, before the cost ceiling stopped
  it. Real spend $2.115, confirmed against the actual Apify dashboard: 17 real actor runs (16
  reddit_search + 1 one-time community lookup, both hit the same `harshmaur/reddit-scraper`
  actor). Root cause: BUG-023's fix (2026-07-07) stopped the planner repeating an *identical*
  query string, but did nothing to detect when *differently-worded* queries return substantially
  the *same* underlying posts — a small subreddit's results converge on the same ~15-20 threads
  regardless of phrasing (confirmed: several exact URLs recurred 5-6+ times across the run's
  combined reference list), and the planner, reading an ever-growing wall of accumulated text,
  couldn't reliably tell "genuinely new" from "same content, reworded."
- Fix: added `consecutive_stale_reddit_calls` to `ContextAgentState`, computed in code (set
  difference of `result.urls` against `state.urls`, never LLM judgment) in `_act_reddit`.
  `decide_next_step` gained a third hard override, same pattern as the pre-existing call-count
  and cost-ceiling checks: after 3 reddit_search calls in a row returning zero new URLs, force
  stop (3 chosen deliberately patient-over-eager, user call — no formula for the "right" number).
  Also tightened `_DEFAULT_MAX_RUN_APIFY_COST` $2.00 -> $1.50 -> $1.00 over the course of this
  session as the actual failure mode became clear. 23 pre-existing tests updated for the new
  required state field/kwarg (mechanical); 3 new regression tests added covering reset-on-new-
  url, increment-on-stale, and the stop override itself.
- Known residual gap, not fixed (low priority, theoretical): the new stale-streak override skips
  straight to finalize, same as the other two hard overrides, even if tavily_search/
  firecrawl_extract were never tried once — unlike the cost/call ceilings (genuine resource
  exhaustion), Reddit going stale doesn't necessarily mean the run is out of budget, so arguably
  it should redirect to try the untried tool once before giving up. Not yet observed to cause a
  real problem in a real run — parked, not scheduled.


### BUG-027 - Path A (auto-scraped events) never gets the same research depth as Path B (manual topic), even after narrowing to survivors
- Date opened: 2026-07-08 (spotted reading `event`/`bundle` output structure from the BUG-026 live test)
- Status: open — explicitly out of scope for now (user call, 2026-07-08: "let's only deal with
  Path B"). Logged so the asymmetry is a documented, deliberate scope boundary, not a silent gap.
- Feature: `scripts/pitch_angles.py`'s `run_pitch_pipeline`, comparing Path A (`scraper.fetch()` +
  `EventExtractor.extract()`) against Path B (`ContextAgent.gather(topic)`).
- Behavior: Path A scans several subreddits (`ApifyRedditScraper`, ~7 subs x ~4 posts), builds
  each `TrendingEvent.reaction_sample` directly from the top 8 real comments per post at scrape
  time — no research loop, no `ContextBundle`, `bundle=None` for every Path A event, always.
  `EventExtractor` then picks the best `top_n` (default 3) via one LLM call, and those survivors
  go straight to `gap_agent`/`story_pitcher` with no bundle — no summary, no key_moments, no
  background-fact resolution, no unresolved-facts check. Path B's `ContextAgent.gather()` runs
  the full iterative research loop (reddit_search/tavily_search/firecrawl_extract, multiple
  rounds) on its ONE given topic and always produces a bundle.
- Why this isn't (yet) called a defect: Path A scans dozens of candidate posts before narrowing
  down — running the full multi-tool ContextAgent loop on every scraped post before knowing which
  ones survive `idea_fit_gate` would be far more expensive than the current one-shot scrape. The
  asymmetry only becomes questionable AFTER narrowing to `top_n` survivors (cheap to research
  further at that point) — nothing currently sends those survivors through the same deep-research
  step Path B topics get.
- Decision: not being fixed now. Session scope is Path B only; Path A's research-depth parity is
  a real, legitimate design question for later, not an active work item.


### BUG-028 - test_package_total_10s_accepted builds a 2s shot against a 3s floor, has failed since the floor was raised
- Date opened: 2026-07-15 (hit while running the suite for the director merge, ticket 03)
- Status: FIXED 2026-07-15 (commit below). Was: open, out of scope for the director merge, confirmed
  PRE-EXISTING by stashing the ticket-03 diff and re-running on HEAD.
- Fix: re-based the fixture off the dead 2s shot — `_package([4, 4, 2])` -> `_package([4, 3, 3])`.
  Still totals 10, but every shot now clears the per-shot floor too, so the assertion under test
  (the 10s total envelope) actually runs. Verified it now bites: [4,3,3]=10s accepted, [3,3,3]=9s
  rejected — the floor is live and genuinely exercised, not just green. Also corrected the adjacent
  9s-rejected test's comment, which still claimed "the per-shot floor is 2s".
- Feature: `tests/schemas/test_generation.py::test_package_total_10s_accepted` via its `_shot_spec`
  helper.
- Behavior: the test asks for a package totaling 10s and reaches it with a shot of
  `duration_seconds=2`. `ShotSpec.duration_seconds` is `Field(ge=3, le=8)`, so the helper raises
  `ValidationError` before the test's actual assertion (the 10s total-envelope floor) is ever
  exercised.
- Root cause: the per-shot floor was raised 2 -> 3 on 2026-07-12 (a 2s shot cannot fit a readable
  action — pitch-43's 2s/3-action hook rendered smeared). The product-envelope test was not
  re-based onto the new floor, so it still composes 10s the old way.
- Why it matters beyond a red square: the 10s total floor is currently UNTESTED. The test that
  claims to cover it dies in its fixture, so a regression in `_check_total_duration` would not be
  caught. This is a false sense of coverage, not just a broken test.
- Fix (not applied): re-base the fixture onto durations that are legal per-shot and still total 10
  (e.g. 3+3+4), so the assertion under test actually runs.


### BUG-029 - the voiceover path is still live in code with no kill-switch; only a prompt convention keeps it silent
- Date opened: 2026-07-15 (examined while merging PLAN+SCENE into the director, ticket 03 — the PRD
  required narration_line be examined rather than carried into the director unexamined)
- Status: open — deliberately out of scope for ticket 03 (PRD: "Log and fix separately"). The
  prompt half was addressed in passing; the assembly half is untouched.
- Feature: `src/generation/assembly.py` (TTS + mix), `ShotSpec.narration_line`, and the writer's
  beat gate in `src/generation/content_writer.py`.
- Behavior: the product is pure picture + native sound (native-quality-v2, locked 2026-07-07) — no
  voiceover of any kind. But assembly still calls TTS and mixes narration whenever
  `narration_line` is non-null, with NO global kill-switch. Nothing enforces the product rule; the
  only thing keeping the product silent is a CONVENTION — the pitcher's prompt says narration_line
  is "retired, LEAVE THIS NULL", and the writer's gate (`draft.narration_line if
  beat.narration_line is not None else None`) then drops whatever the director wrote.
- Consequence: a stale pre-pivot `story_json` row (written while narration was still a real field)
  would pass `beat.narration_line is not None`, survive the gate, and ship real voiceover into a
  no-voiceover product. This is the same shape as the bug the whole director-stage PRD exists to
  fix: a product guarantee resting on an LLM instruction instead of code.
- Partially mitigated 2026-07-15 (ticket 03): the merged DIRECTOR prompt no longer instructs
  narration composition (PLAN's "2.2 words per second" rule); it mirrors `hook_text` with
  "ignore — always return null". Live-path behavior is unchanged (the beat gate already dropped it);
  a legacy row is now strictly safer, because the director returns null even when the beat carries
  text. The DEFECT REMAINS: the guarantee is still a prompt instruction plus a gate keyed on the
  stale beat, not a code-level switch.
- Fix (not applied): a single explicit no-voiceover switch at assembly, so the product rule is
  enforced where the audio is actually mixed rather than three stages upstream.
