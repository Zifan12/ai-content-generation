# Domain Glossary

## Blueprint

A structured schema describing the viral mechanics of a short-form video. Used in two directions:

- **Extraction (descriptive):** populated from an observed scraped video. Extractor reads transcript + metadata + hashtags + cover, emits Blueprint.
- **Generation (prescriptive):** consumed by the generation pipeline. Prompt engine + script writer read Blueprint, emit new video assets.

Every field must be both **observable from a finished video** AND **actionable by the generation pipeline**. Round-trip lossless.

Versioned via `EXTRACTOR_VERSION` string. Current: `v3`. Stored in `blueprints` table with unique constraint `(content_item_id, extractor_version)`.

Two tiers:

- **Universal mechanics** — niche-agnostic fields (hook type, pacing, loop quality, etc.)
- **Niche-conditional** — fields that depend on `niche_label`, plus free-text `aesthetic_descriptors: list[str]` and free-string `niche_label: str` metadata.

## Niche

A named bundle of seed hashtags + keywords used for scraping a content category. Stored as a row in the `niches` table with fields: `name`, `keywords`, `hashtag_seeds`, `is_active`. Attached as a free-string `niche_label` on extracted Blueprints for filtering and retrieval.

Niches are **runtime parameters**, not architectural primitives. They shape **content** (what to scrape, what label to attach), not **structure** (schema is identical across niches). A niche row does NOT carry schema-shaping data — the Blueprint schema is one shape; "niche-conditional" means the extractor LLM interprets free-text fields like `aesthetic_descriptors` in the niche's vocabulary, not that the field set changes.

Primary test fixture niche: `surreal_hyperreal`. Reference niches retained for ablation only: `brainrot`, `anime_ai`, `horror_ai`.

## aesthetic_descriptors

A `list[str]` field on each Blueprint. Free-text tags emitted by the extractor LLM describing the visual/tonal feel of a video (examples: `["liminal", "mirror-glitch", "uncanny-skin"]`).

Used in two ways:

- **Retrieval signal:** RAG retriever uses descriptor overlap as fuzzy match between target generation request and candidate Blueprints.
- **Prompt fragments:** Generation pipeline literally concatenates retrieved descriptors into image/video model prompts (e.g. Seedance, Kling).

Free-text by design — closed enums would prevent literal injection into prompts. Risk: extractor drift across synonyms (`weird` vs `weirdcore` vs `weird-vibe`). Open question: should descriptor consistency be scored on the eval gate?

## share_hook_type / comment_bait_type

Two enum fields on the Blueprint replacing the originally-spec'd `share_trigger` / `comment_trigger`.

- `share_hook_type: enum("relatable", "shocking", "useful", "aspirational", "humor", "none")` — the content property that tends to drive shares.
- `comment_bait_type: enum("question_to_viewer", "controversial_take", "incomplete_info", "identifiable_error", "none")` — the content pattern that tends to drive comments.

Reframed from "trigger" → "hook/bait type" so the field describes an **observable property of the video**, not an attribution of viewer motive. Generator can deliberately produce these patterns; extractor can score them from transcript + cover + comments. Closed enums (unlike `aesthetic_descriptors`) so kappa can score extractor agreement on the eval gate.

## hook_type / hook_subtype

`hook_type` is a Tier 1 (universal) axis on the Blueprint. In **v3 it is open-string**, mirroring the v0→v1 bootstrap pattern: ship as free text first, then close to a Literal enum in v3.1 after the surreal_hyperreal scrape (200 items) lands and the LLM has converged on a stable value set.

Observed-but-not-locked candidate values from the 120-item v1 corpus across `anime_ai` / `brainrot` / `horror_ai`:

- `visual_aesthetic` — strong visual feel, no claim/question
- `visual_pattern_break` — jolt/cut/anomaly opens
- `curiosity_gap` — withhold-then-reveal framing
- `shocking_claim` — bold statement opens
- `direct_promise` — "I will show you X"
- `emotional_hook` — direct emotional appeal

These are NOT a v3 enum — surreal_hyperreal may surface new patterns (e.g. `slow_reveal_uncanny`). Lock to enum only after Task 14 scrape, with the 7-value-or-fewer + cross-niche-reuse criteria the v1 corpus met.

`hook_subtype: str | None` is a Tier 2 (niche-conditional) free-text companion that captures niche flavor (v1 examples: `"anime_transformation"`, `"retro internet aesthetic"`). Always free-text. Not kappa-scored.

**Eval gate (Task 12) implication:** `hook_type` is dropped from kappa scorers in v3. Other closed enums (e.g. `primary_emotion`, `share_hook_type`, `comment_bait_type`) remain kappa-scored.

## Dropped from v1 → v3: LLM-emitted float scores

The v1 schema had 7 floats in `[0.0, 1.0]` (`hook_strength`, `curiosity_gap`, `immediate_clarity`, `emotional_charge`, `payoff_quality`, `replayability`, `comment_trigger`, `shareability`) emitted by the extractor LLM as self-ratings. **All dropped in v3.**

Reasons:

- **Round-trip fails:** not actionable — the generator cannot "aim at 0.83 curiosity_gap".
- **Unmeasurable noise:** Cohen's kappa doesn't apply to continuous values; no eval-gate scoring possible.
- **Dead signal:** `MECHANIC_FIELDS` constant declared in `src/evals/blueprint_eval.py` is never consumed by any code path.
- **Redundancy:** `curiosity_gap` float duplicates the candidate `hook_type="curiosity_gap"` enum value.

If continuous virality signal is needed later (ML predictor P4), derive it from real **outcome metrics** (`view_count`, `outcome_view_percentile` from the Publish Loop P3.5) rather than LLM self-rating.

The `confidence: float` self-rating field from v1 is dropped in v3 for the same reasons: LLM self-rating, noisy, not actionable, not kappa-able.

## primary_emotion

Tier 1 closed `Literal` enum carried unchanged from v1 into v3 (9 values): `awe`, `surprise`, `tension`, `humor`, `anger`, `anxiety`, `aspiration`, `satisfaction`, `relatability`.

Validated against the v1 corpus of 120 items: all 9 values appeared, no "other" overflow, and each existing niche has a clear dominant emotion (anime_ai → `awe`, brainrot → `humor`, horror_ai → `tension`). Predicted dominant for `surreal_hyperreal`: `awe` (uncanny visuals) + `anxiety` (liminal/dread tone) — both covered.

Kappa-scored on the eval gate.

## New Tier 1 fields in v3 (open-string in v3, enum-locked in v3.1)

Five new universal Blueprint fields added in v3. All ship as open `str` in v3 — values free-emitted by the extractor LLM — then locked to closed `Literal` enums in v3.1 after the surreal_hyperreal scrape (Task 14) provides convergence evidence, mirroring the v0→v1 bootstrap pattern.

- `pacing: str` — cut frequency / energy curve (e.g. `slow | medium | fast | frenetic`).
- `loop_type: str` — how the video loops (e.g. `seamless | hard_cut | open_ended | repetitive`). Renamed from `loop_quality` to avoid implicit quality judgment.
- `audio_type: str` — character of the audio track. Renamed from `audio_character` for naming consistency with `hook_type`.
- `visual_complexity: str` — density of visual elements (e.g. `low | medium | high`).
- `color_mood: str` — dominant color tone (e.g. `warm | cool | desaturated | saturated`).

## duration_band

Tier 1 closed `Literal` enum carried unchanged from v1 into v3 (5 values): `under_10s`, `10_20s`, `20_40s`, `40_60s`, `over_60s`.

Required for round-trip: generator needs a target length when producing a new video from a retrieved Blueprint. Was incorrectly listed for removal in plan Task 12; reinstated. Kappa-scored on the eval gate.

All pass the round-trip rule (observable from video + actionable by generator) and the universality rule (every niche has pacing, audio, etc.). Kappa-scored on the eval gate only after they become closed enums in v3.1.

## Why kappa scoring exists

Cohen's kappa scores agreement between two label sets on the same items. Used here to detect noisy LLM extraction: same extractor run twice on the same 30-video sample should produce the same labels.

Three roles:

- **Eval gate** — CI rejects schema where field reliability drops (kappa < 0.6). Prevents shipping noisy extractor that breaks downstream RAG/ML.
- **Field-design feedback** — low kappa signals overlapping enum values. Triggers schema redesign.
- **Bootstrap completion signal** — Phase 2 closes open-string fields to enums only after kappa ≥ 0.6 on a 30-sample re-run. Below that, field stays `str`.

Kappa applies to **closed enums only**. Floats (use intraclass correlation) and free-text strings (no defined equivalence) are not kappa-scored — one reason why both were dropped or kept open in v3 design decisions.

## Tier 2 fields in v3 (niche-conditional)

Tier 2 is deliberately minimal — 3 fields. The `aesthetic_descriptors: list[str]` field absorbs most per-niche flavor as free-text, avoiding schema bloat from adding more per-niche-specific fields. v3 is the bootstrap baseline; new Tier 2 fields can be added in v4 if extraction data shows a real gap.

- `aesthetic_descriptors: list[str]` — free-text tags, dual use for RAG retrieval signal + prompt fragments.
- `niche_label: str` — free-string label attached to the Blueprint, joined to a `niches` table row (e.g. `surreal_hyperreal`).
- `hook_subtype: str | None` — free-text companion to `hook_type` capturing niche flavor (v1 examples: `"anime_transformation"`, `"retro internet aesthetic"`).

## SYSTEM_PROMPT

The persistent instruction document passed as the `system` parameter to every Sonnet extraction call. Lives as a module-level constant in `src/blueprints/extractor.py`. Distinct from the per-item `envelope` (caption + transcript + metadata).
_Avoid_: "prompt" without qualifier — ambiguous between SYSTEM_PROMPT and envelope.

## envelope

The per-item user message sent on each extraction call. Built by `BlueprintExtractor._build_envelope` from `RawContentItem` metadata + optional transcript + niche label. Always changes between items by construction.
_Avoid_: "user prompt", "input"

## content-business test

The P3.5 30-post publish run, dual-purposed as a time-boxed experiment judging whether the content channel has distribution traction (NOT revenue — too small to read early). Day-14 soft check; day-30 hard verdict, default **portfolio-only** unless a lean-in criterion fires (clear upward view trend, ≥1 ~50K+ breakout, or followers ≥500 and climbing). Verdict + numbers recorded in a learning note. Defined in `docs/superpowers/specs/2026-06-09-hybrid-monetization-strategy-design.md`; exit criteria live in PLAN.md Step 3.5.6.

_Avoid_: "monetization test" — the test measures traction, not money.

## Deferred decisions (P5 agent layer)

The following are NOT decided. Defer until P5 spec writing (post-P3.5). Decisions made earlier would be guesswork — context too thin.

- **Agent framework:** Pydantic AI vs LangGraph vs raw Anthropic SDK tool-calling. `langgraph>=0.2.0` currently in `pyproject.toml` from speculative P0 stack pick; not yet imported anywhere.
- **Multi-agent vs single agent:** Roadmap line 184 implies single ReAct loop ("0 code-level branching, all routing is LLM-driven"). Default = single agent unless P5 scope reveals genuine role separation.
- **Pydantic AI adoption scope:** If picked, applies only to P5. BlueprintExtractor stays on `instructor` + `anthropic` SDK (shipped, cache-tuned, 438 rows extracted).

Re-open when writing `docs/superpowers/specs/<date>-phase-5-agent-orchestrator.md`. Not before.
