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

## Content Writer (P3)

The generation-side counterpart to the Blueprint extractor: turns a **premise**
(+ optional RAG-retrieved viral neighbors for style/lane grounding) into a validated
ContentPackage (`src/generation/content_writer.py`, schema `src/schemas/generation.py`).

Paradigm = **single-shot believable micro-narrative** (locked 2026-06-22, "Option A";
supersedes the 2026-06-10 chained-continuity / 3-shot paradigm, which manufactured
incoherent "3 strangers" slop). One video = ONE continuous take (~8s, vertical 9:16,
photoreal, `surreal_hyperreal`) in which a small dramatic thing happens and PAYS OFF —
a "wait, is this real?!" found-footage moment, NOT a wordless impossible tableau and NOT
a montage. No cuts, no last-frame handoff, no stitch. Content lane is a market-resolved
bet (the structure is well-founded; the eye-gate is the floor, the P3.5 market the ceiling).

**One-pass, model-aware:** a single LLM call. The writer is fed the routed model's dialect
(DATA from `config/render_rules.yaml`, not per-model code) and writes the final
**model-native** prompts directly — there is no separate prompt-builder layer (the old
`builders/` classes are deleted). v1 routes to one default model (`veo3_1`, Veo 3.1 high);
a premise-classifying router is deferred.

Key fields (single-shot `ContentPackage`): one **`shot`** (a `Shot` carrying `start_keyframe`
= the one photoreal opening still, subject-first, no palette; `motion` = the continuous move
that builds to the payoff, including an **`Audio:` line** of concrete diegetic sound; optional
`end_keyframe`); **`model_cli_id`** (the motion model the prompts target); **`premise`**
(provenance, code-set); **`mood_anchor`** (palette + lighting + realism, appended at render to
the still); **`onscreen_text`** (the one text-hook line — a MANUAL post overlay at upload, since
the model can't render text reliably); `caption`; `hashtags`; `voiceover` (rare diegetic
dialogue → model `Dialogue:` line, default None). The old `device` 7-menu, `device_rationale`,
and the chain-contract `model_validator` are all removed.

_Avoid_: "chained continuity", "segment", "3-shot", "handoff", "device menu" — retired 2026-06-22.

## Premise source — reaction-driven cultural monitoring (current: 2026-06-27, was 2026-06-23)

Where the writer's **premise** comes from. Superseded twice: grounded `premise_generator.py` and pure imagination (both shelved 2026-06-23), then the 2026-06-23 news-reactive design itself narrowed to **reaction-driven** on 2026-06-27 (any recognizable fictional character mid-reaction-wave, not just news). `src/monitor/` is BUILT and live (not planned): a scraper/event extractor watches Reddit for trending events (Path A) or a **Context Agent** researches a user-given topic (Path B, `--topic`); an **Idea-Fit Gate** screens for mode + heat + recency; a **Gap Agent** reads the reaction and names the *unmet desire*; a **Story Pitcher** proposes a slate of distinct takes; a **Story-Craft Gate** judges each pitch against craft rules (bounded-retry repair on failure). The human approves one; its take becomes the writer's premise. Full pipeline detail lives in this repo's `CLAUDE.md` (Architecture section), not here — this entry is vocabulary only.

_Avoid_: treating "imagination-led premise", "grounded premise", or "news-reactive" (narrower than the current reaction-driven scope) as the live path.

## Gap (audience-reaction)

The specific **unmet desire** behind a trending reaction — what the audience would be satisfied by if it existed. Output of the Gap Agent (`GapAnalysis`: `dominant_emotion`, `audience_want`, `evidence_quotes` [0-3 verbatim quotes], `reasoning`). `audience_want` is phrased in the model's own words, never copied reaction slang — that's what `evidence_quotes` is for. When the reaction never states the want outright, the agent is licensed to hypothesize it from context/genre convention, and must hedge in `reasoning` when the hypothesis rests on an unresolved fact. Hard rule: a gap is a *positive desire* ("people wanted the climax they were teased and never got"), NOT a negative reaction ("people hated the ending"). Optionally grounded by a `ContextBundle` (Path B research) appended to the prompt.

_Avoid_: `gap_type` enum, `producibility_score`, `virality_window_hours` on `GapAnalysis` — all retired; `virality_window_hours` lives on `TrendingEvent` only.

## Story Pitch

One of 2-3 distinct creative takes the Story Pitcher proposes per gap (`StoryPitch`: `logline`, `mode` [wish | satire | other], `characters`, `desired_moment`, `scene_setting`, 3-5 `beats` [`StoryBeat`: role, visual_line, shot_size, optional dialogue], `caption_policy`, `hook_line`, `why_it_lands`, `legal_flag`). Craft rules enforced at validation: beats can't all share one `shot_size`, at most one `hero_moment` beat, `hook_line` present iff `caption_policy` is `hook_only`. `legal_flag` marks real-person/IP likeness.

_Avoid_: "Angle Pitch" / `AnglePitch` / `render_backend` / `estimated_cost_credits` — the routing-era model, removed in the Task 7 orchestration swap. Current term is Story Pitch.

## Scene Space (one-space rule)

The single continuous physical space a Story Pitch's ENTIRE story happens in —
what `scene_setting` names (locked 2026-07-12, corpus-derived: every worked
multi-shot example in `ai_video_resources` stays in one space; scene-to-scene
consistency is measurably harder for the render model than face consistency).
A Scene Space is **one anchored location, optionally plus ONE adjacent,
visibly-connected threshold** (a door, window, the hallway just outside),
crossed **at most once as part of the action** — never via a cut that teleports
past the threshold's sightline. Nothing beyond the threshold's sightline exists
in the story.

Legal: bedroom + its doorway, crossed once during the drag-back-inside beat.
Illegal: bedroom shots intercut with a far corridor and a separate hallway
(the pitch-43 failure, 2026-07-12: 4 spaces in 15s read as incoherent).

_Avoid_: "location" unqualified — ambiguous between Scene Space (this, the
story-level constraint) and the location REFERENCE (`location_slug` +
`world_anchor`, the render-grounding asset for the anchored location).

## Web-research Fridge

The store of **raw web-research text** the Context Agent gathered (tavily_search + firecrawl_extract combined — the `web_text` state field) but *discarded* when it compressed everything into the `ContextBundle`. The Fridge re-captures that raw material — chunk → BGE-M3 embed → pgvector (`WebResearchChunk` table) — so a downstream stage can `retrieve()` a specific gathered-but-summarized-out fact on demand (`src/monitor/fridge.py`). v1 = **within-run, web-text only**; reddit already travels the chain uncompressed in `ContextBundle.reaction_sample`, so the Fridge does not re-store it. Populated **Path B only** (Path A gathers no web research).

The load-bearing distinction: **`web_text` (raw) and `ContextBundle` (compressed) are two different things and travel separately** — `gather()` hands back the raw text as its own return value, never folded into the bundle (the bundle is what gets persisted to the DB; putting raw in it defeats the compression the Fridge exists to recover from).

_Avoid_: calling the raw field "tavily_text" (renamed to `web_text` 2026-07-10 — it holds firecrawl text too); treating the Fridge as a cross-run cache (v1 is within-run).

## Pitch Grounding (coherence check)

The check that asks whether a Story Pitch **contradicts the source's canon** — NOT whether it is faithful to it. A pitch (any mode — wish/satire/other) deliberately invents content that never happened; that invention is the product. So this is a **coherence** judgment: would a fan who knows the source accept the pitch as consistent with the established world/characters, or reject it as nonsense. **Canon = the retrieved Fridge chunks** (best available approximation of source truth).

**The load-bearing rule: fail ONLY on CONTRADICTION, never on absence.** Canon silent on something = PASS (that is the invention, by design); canon that directly clashes with an assumed premise = FAIL. Conservative ceiling: can only catch a contradiction whose contradicting fact is actually in the retrieved canon. Implemented as a fixed 2-call RAG pipeline (derive assumed-canon queries → retrieve → judge contradiction-only → `{coheres, conflicts}`), deliberately **not** an agent (`src/monitor/pitch_grounding.py`).

_Avoid_: "faithfulness check" / "unsupported-claims check" / "fact-check" — all the dead earlier framing; the invented moment is not an unsupported claim, it is the point. Do NOT search the web on a conflict in v1 (deferred agentic upgrade).

## Voice Profile

A **standing per-character asset** describing *how a character speaks* — the writer's counterpart to the character's key-art (which fixes how they *look*) and to a location's `world_anchor` (which fixes a *place*). Lives beside the image refs at `refs/<char_slug>/voice_profile.md`. Built ONCE per character at onboarding (manual `gen_voice_profile` script), grounded in the character's fetched canon (Fandom **Personality** section + a few real **Quotes**) which an LLM **compresses** — never recalls from training memory — into three light markdown sections:

- **Fingerprint** — the constant texture: diction, sentence shape, verbal tics, how they address people.
- **Modulation** — how the voice *flexes* by emotion (angry / tender / triumphant) — resolves "nobody speaks one fixed way".
- **Anti-patterns** — 2-3 `WRONG → RIGHT` pairs, each forced through the **wrongability test** (a line that could describe 100 characters is too vague).

Consumed at **pitch time**: the pipeline loads the profile for each named character (via `_slug`) and injects the ones that exist into the Story Pitcher, which authors the beat's `dialogue_line` in-character. A character that *has* a profile is a **profiled character**; only profiled characters may be given dialogue (an unprofiled character stays silent rather than speaking generically). The **cast** is the de-facto set of onboarded characters — there is no registry table; `refs/` folders ARE the cast.

Scope (locked 2026-07-11): **verbal identity only** — the *words + delivery* a character uses. It does NOT lock the heard audio **timbre**; Seedance 2.0 has no cross-render voice lock, so timbre drifts render-to-render (voice-clone continuity is a deferred follow-up feature).

_Avoid_: "voice" without qualifier — ambiguous between **verbal identity** (this, buildable now) and **audio timbre** (deferred, not controllable across Seedance renders). Not a personality bible / SOUL.md (that is a 2000-word human digital-twin doc; this is a ~200-word spoken-line profile).

## Executor

The render runner (`src/generation/executor.py`, new in the single-shot rebuild) — the piece
previously only *declared*, never built. Consumes the adapter's two `RenderJob`s and actually
produces a clip: run the still job (`nano_banana_2`) via the Higgsfield CLI → feed its result
image as the `--image` of the motion (i2v) job (`veo3_1`) → wait → download. `dry_run` returns
cost only (no spend); states credit cost before any paid call; `ffprobe`s the downloaded clip to
confirm the native audio stream (`emits_audio` per model in `render_rules.yaml`). Single-shot ⇒
no stitch step.

_Avoid_: calling this the "render adapter" — the adapter only *declares* jobs; the executor *runs* them.

## Writer eval (rubric v1)

**Status (2026-06-22): PARKED behind the single-shot rebuild.** Built for the retired 3-shot
chain writer; its code-checks (`no_palette_in_keyframes`, `device_requires_event_beat`, …) and
judge dims (`development`-mandatory, `device_execution`) assume the chain grammar that no longer
exists. Left in place (`src/evals/`, `config/writer_rubric*.yaml`) — **not deleted, not run** —
as a possible future "not-broken" lint. The live judge of the single-shot product is the human
**eye-gate** (4-point: idea / believable / not-broken / better = post-worthy floor) + the **P3.5
market** (7-day views = virality ceiling). The description below is retained for that future
repurpose.

Two-tier evaluation of writer output (`src/evals/`, driver `scripts/run_rubric_eval.py`):

- **Code-checks (free):** deterministic per-package rules — no_scale_comparison,
  no_quality_incantations, no_palette_in_keyframes, no_style_words_in_motion,
  device_requires_event_beat (transformation/time_compression must carry an end_keyframe).
- **LLM judge (paid, Opus):** 4 anchored 1-5 dimensions in `config/writer_rubric_v1.yaml`
  — premise_fidelity, development (inverted for the chain: development is now MANDATORY),
  device_execution (carries the device-routing cap), vividness.

A third tier exists for negative-control testing — the **floor probe**: a hand-authored
bad fixture (`data/golden/writer_floor_static.jsonl`, local-only) fed via
`run_rubric_eval --fixtures` and locked by a gated pytest (`tests/evals/test_judge_floor.py`,
runs only under `RUN_PAID_EVALS=1`). The fixture is structurally legal + code-check-clean
but semantically empty; the judge must score it low on the dims it sabotages
(development ≤ 2, vividness ≤ 2). Proves the judge can detect bad work, not just confirm good.

Status (2026-06-14): pipeline runs e2e on the chain grammar (4/4 premises route to distinct
devices, 5/5 code-checks pass, paid judge runs clean). The earlier all-5.00 no-discrimination
gap is now HALF-closed: the floor probe confirmed the judge CAN discriminate (bad fixture →
development=1, vividness=2). The CEILING half — no gradient to rank good-vs-great among
competent packages — is still open, deferred to a dedicated calibration plan. See
`docs/learnings/2026-06-08-rubric-v1.md` Findings 2-3.

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

The following are NOT decided. Defer until P5 spec writing (post-P3.5). Decisions made earlier would be guesswork — context too thin. **(2026-06-23: the P5 agent's *use case* is now concrete — the news-reactive front-end `src/monitor/`. The framework choice below is still deferred.)**

- **Agent framework:** Pydantic AI vs LangGraph vs raw Anthropic SDK tool-calling. `langgraph>=0.2.0` currently in `pyproject.toml` from speculative P0 stack pick; not yet imported anywhere.
- **Multi-agent vs single agent:** Roadmap line 184 implies single ReAct loop ("0 code-level branching, all routing is LLM-driven"). Default = single agent unless P5 scope reveals genuine role separation.
- **Pydantic AI adoption scope:** If picked, applies only to P5. BlueprintExtractor stays on `instructor` + `anthropic` SDK (shipped, cache-tuned, 438 rows extracted).

Re-open when writing `docs/superpowers/specs/<date>-phase-5-agent-orchestrator.md`. Not before.
