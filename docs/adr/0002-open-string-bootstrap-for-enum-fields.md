# Open-string bootstrap for new Blueprint enum fields

New universal Blueprint fields introduced in v3 (`hook_type`, `share_hook_type`, `comment_bait_type`, `pacing`, `loop_type`, `audio_type`, `visual_complexity`, `color_mood`) ship as open `str` rather than closed `Literal[...]` enums, and are closed to enums only in v3.1 after the `surreal_hyperreal` apidojo scrape (Task 14) provides convergence evidence. Locking enum values now would force surreal_hyperreal content into taxonomies derived from `anime_ai` / `brainrot` / `horror_ai` v1 data — wrong-niche evidence.

The bootstrap process is the same one the project already used for v0 → v1: ship open, observe LLM convergence on a real corpus (Counter-by-niche analysis), lock to enum, then re-extract under the closed schema once kappa ≥ 0.6 on a 30-sample re-run.

## Consequences

The v3 eval gate kappa-scores only the two fields that ship closed in v3 — `primary_emotion` and `duration_band`. Coverage of the eval gate is temporarily reduced. Phase 2 (post-Task 14) reopens the grilling round, locks values from observed LLM emissions, bumps `EXTRACTOR_VERSION` to `v3.1`, and re-extracts all 320 items (~$4.50 Sonnet) under the closed schema.

## Considered alternatives

**Lock enum values now from the v1 corpus** — rejected because the v1 corpus is clockworks-scraped `anime_ai` / `brainrot` / `horror_ai` content, while the primary v3 test-fixture niche is `surreal_hyperreal` (not yet scraped). Forcing surreal_hyperreal content into anime/horror taxonomies during extraction would produce inflated `notes` overflow and would miss surreal-specific patterns (e.g. `slow_reveal_uncanny` as a hook style).

**Defer the v3 schema until after the scrape, then lock everything in one shot** — rejected because it blocks Tasks 1–8 (niche seed, migration, scraper rewrite, model rewrite, tests, scraper) that don't depend on enum values being locked. The open-string approach lets the scraper, model, and migration land first, then closes the schema once data is in hand.
