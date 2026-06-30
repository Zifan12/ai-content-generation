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

