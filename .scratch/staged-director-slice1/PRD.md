# Slice ① — Slim pitcher, D1 director-script stage, craft-gate relocation

Status: closed (shipped 2026-07-16 — commit 7b54edc, feat(pipeline): staged director slice 1: desire-only pitcher + StoryArchitect D1 stage)

## Validation evidence (2026-07-16)

- pytest: 614/614 passed, 1 skipped (incl. new tests/generation/test_story_architect.py, rewritten pitcher/orchestration/schema suites)
- ruff: all slice-touched files clean; repo total 34 (2 over the documented ~32 baseline — both in files untouched by this slice: tests/rag, src/models/niche+trend; pre-existing drift)
- mypy src/: 17 errors, ZERO in slice-touched files (all pre-existing in dormant scrapers/blueprints modules)
- Migration a7c2e91d4b58 (idea_json) applied to local Postgres.
- Two-axis review (standards + spec sub-agents): no hard standard violations; _gap_block/_event_block duplication fixed (src/monitor/prompt_blocks.py); stale hook_text docstring fixed.
- **Live free verify (event 17, pitch-51's premise): PARTIAL-PASS.** repitch_event --event-id 17 --choice 1 ran the full new chain live: pitcher emitted a 3-idea desire-only slate (no beats — obs 2206 defect class structurally impossible now), architect developed the pick into a 5-beat script with correct spine fields (destinations + full flowing required_actions, one legitimate None) and an in-character Elfaria dialogue line (floor satisfied), gates passed, pitch 54 persisted (idea_json + story_json) + handoff written. Writer leg stopped by the PRE-EXISTING reference gate: the new story's cast includes Zeo, who has no key-art in refs/ — "Reference check failed — nothing spent." Not a slice defect (same gate blocks any pipeline version for this cast); the writer's input surface is unchanged (identical beat schema) and covered by its green copied-from-pitch suite. Writer-leg diff completes once Zeo key-art lands (asset work, slice ③ territory).

## Known cosmetic follow-ups (slice ② cleanup list)
- pitch_grounding.py still names its input "pitch" (works via the StoryPitch=StoryScript alias; judges the script now — D7 decided on evidence).
- @traced on pitcher/architect omits kind="generation" (pre-existing pattern on the pitcher; fix both together).
- run_playbook_ablation.py / run_fridge_phase0.py are runtime-broken against the slim pitcher (already were the moment the contract changed); StoryPitchSlate kept only so their imports resolve — delete scripts + class together.
Date: 2026-07-16
Design docs: `docs/superpowers/specs/2026-07-16-staged-director-brain-design.md` (parent architecture, LOCKED) + `docs/superpowers/plans/2026-07-16-slice1-slim-pitcher-d1-stage.md` (both gitignored; this PRD is the durable record)
Prior art: `.scratch/director-stage/PRD.md` (2026-07-15) — its guarantees carry forward, see Implementation Decisions D9-D11.

## Problem Statement

The pitcher authors story beats — shot sizes, destinations, required actions, dialogue — while being the one stage with no render knowledge. The measurable consequence: pitch-51's beat-free lift line was authored by the pitcher (obs 2206); render defects are born upstream of every stage that could catch them.

Underneath it sits an architecture problem the user named directly: "we just keep adding more information into a SYSTEM_PROMPT." Five kinds of knowledge (universal film craft, AI-translation craft, measured model envelope, per-story world facts, failure lessons) accrete into monolithic prompt constants. Measured failure modes: prompt bloat, story-term leakage biasing future unrelated stories (23+ instances found 2026-07-16), and no way to attribute which instruction earns its tokens. A Second Brain consult (Chip Huyen, Domain 14) confirmed the architecture is wrong: knowledge must route by how often it changes, not pile into one string.

## Solution

One owner per craft. The pitcher slims to what it is good at: naming the DESIRE (the moment a reaction wave is begging to see). A new director-script stage (D1) — the first stage of the staged director brain — turns the user-picked idea into a full story script (beats, dialogue, scene setting), holding the story-craft knowledge and the per-story world knowledge (canon context, character voices) the pitcher never had. The story-craft gate moves with the beats: it judges scripts now, not pitches. The writer downstream consumes beats in the identical schema it already reads, so the render path is untouched.

From the user's perspective: pick from a short list of IDEAS instead of pre-built beat sheets; the one you pick gets developed by a stage that actually knows story craft and the character's canon; everything after that behaves as today.

## User Stories

1. As a studio operator, I want the pitcher to hand over only the idea (logline, mode, characters, desired moment, why it lands), so that story structure is authored by the stage that owns story-craft knowledge.
2. As a studio operator, I want to pick the winning idea BEFORE any script is written, so that I judge a short desire-list cheaply and only pay for developing the winner.
3. As a studio operator, I want the director-script stage to author the beats, so that shot sizes, destinations, and required actions are chosen with craft knowledge rather than guessed by the pitcher.
4. As a studio operator, I want the director-script stage to receive the context bundle (canon research), so that the story it builds coheres with the source work's facts.
5. As a studio operator, I want the director-script stage to receive character voice profiles, so that dialogue lines sound like the characters rather than generic speech.
6. As a studio operator, I want the story-craft gate to judge the finished script with its existing rubric and bounded repair loop, so that script quality is enforced exactly where scripts are now born.
7. As a studio operator, I want the beats to reach the shot-prompt writer in the identical schema used today, so that the battle-tested render path does not change in this slice.
8. As a studio operator, I want the repitch utilities to keep working against the new stage layout, so that I can re-develop an event without re-scraping.
9. As a studio operator, I want a free, zero-credit verification (rerun a past premise end-to-end and diff the shipped scene lines), so that I can validate the restructure before any paid render.
10. As a studio operator, I want dead on-screen-text fields (caption policy, hook line) verified and removed during the slim, so that the schema stops advertising a product surface the native-quality-v2 pivot deleted.
11. As a studio operator, I want the director-script stage's credit/token cost estimated before a run like every other seat, so that cost governance holds at the new stage.
12. As a developer, I want the new stage behind one seam that mirrors the pitcher's (idea + knowledge in, script out), so that the FakeLLM test idiom transfers unchanged.
13. As a developer, I want the beat schema's validators and spine fields carried over untouched, so that the 2026-07-15 spine guarantees survive the relocation.
14. As a developer, I want the one-continuous-move rule and the destination/required_action field specs moved verbatim into the new stage's instruction, so that relocating beat-authoring does not silently rewrite beat semantics.
15. As a developer, I want the paraphrase-free structural test re-pointed across the new stage boundary, so that no intermediate paraphrase hop can be reintroduced without a test failing.
16. As a developer, I want the new stage configured as a named seat in the provider config, so that its model is a YAML edit like every other seat.
17. As a developer, I want the old thick-pitch schema retired only after all callers migrate, so that the slice lands green rather than half-cut-over.
18. As a maintainer, I want the pitcher's system prompt to shrink to desire-only instruction, so that the measured bloat/leakage surface actually decreases in this slice rather than being deferred.
19. As a maintainer, I want NO lexical spine checks reintroduced, so that the measured 2026-07-15 rejection (word-matching can't read prose) stays honored.
20. As a maintainer, I want this PRD to record which knowledge moved where and why, so that future sessions do not re-derive the routing from renders.

## Implementation Decisions

- **D1 — Pitcher output contract.** The pitch slims to: logline, mode (wish/satire), characters (existing character-reference shape reused), desired_moment, why_it_lands, legal_flag. No beats, no scene_setting, no shot language. Slate stays 2-3 pitches. Far-domain examples stay for the remaining fields (ablation-proved: no examples = broken fields).
- **D2 — Pick point.** User approval happens at the idea level. The director-script stage runs ONCE, on the picked idea only. (User decision, 2026-07-16.)
- **D3 — Script artifact.** New StoryScript model: scene_setting + ordered beats + character look/voice notes + a location requirement (the latter two are forward hooks for the asset stage, slice ③). The beat model itself is UNCHANGED — every validator, spine field, and docstring guarantee carries over as-is.
- **D4 — Beat-craft instruction relocates verbatim.** One-continuous-move, destination/required_action specs, shot-size-variety intent move from the pitcher's prompt to the new stage's prompt with minimal rewording. Rationale: the 07-15 PRD's D4 showed a compressed rule silently changes meaning; relocation must not re-compress.
- **D5 — Knowledge inputs.** The director-script stage receives: the gap analysis, the context bundle (Path B research), and character voice profiles. The world_anchor / location layout stays writer-side (spatial staging is shot-prompt craft, not story craft). Per-story inputs are injected per call and never written into standing prompts (Huyen tiering — the parent design's core rule).
- **D6 — Craft gate relocation.** The gate's input becomes the script; the verdict rubric is unchanged (its ten dimensions are script-level); the bounded repair loop re-targets the new stage. Gap context continues to feed the desire/register dimensions.
- **D7 — Grounding checker placement.** It fact-checks story premises against canon; since story facts now materialize in the script, its natural input moves from pitch to script. Verify its input surface at implementation; if it reads only logline-level claims it may stay pitch-side. Decide on evidence, not assumption.
- **D8 — Seat + cost.** New named seat for the stage in the provider config, same model tier as the pitcher. Pre-run credit estimation mirrors the pitcher's existing estimator (ADR-0007 estimate-before-spend). Net cost expectation: flat or down — beats were authored 3x per slate, now once.
- **D9 — Paraphrase-free guarantee (carried).** The beat author's output reaches the writer with no intermediate paraphrase stage. The existing structural test re-points at the new boundary. Never deleted.
- **D10 — No lexical spine checks (carried).** Built, measured, rejected 2026-07-15. Do not re-propose substring/overlap checks on scene lines.
- **D11 — Legacy on-screen-text fields.** caption_policy / hook_line are expected dead under native-quality-v2 (no on-screen text). Verify nothing live reads them; delete with the slim if confirmed dead; keep and flag loudly if not.
- **D12 — Old schema retirement.** The thick pitch model and its slate retire only after pitcher, gate, writer, orchestration, and repitch callers all migrate. The slice ends with the suite green and the pipeline runnable end-to-end.

## Testing Decisions

- **What makes a good test:** assert on the artifact a stage returns at its public seam — never on prompt text, call counts, or intermediate structures. The one exception is the structural paraphrase-free test, which pins DATA FLOW (beat fields arrive unmediated), not prompt wording.
- **Seams (confirmed by user 2026-07-16):** four existing — pitcher (output type changes), craft gate (input type changes), writer (input type changes), schema validators (direct construction). Exactly ONE new seam: the director-script stage (idea + knowledge in, script out), mirroring the pitcher's seam shape.
- **Test idiom:** FakeLLM returning queued structured outputs by response-model type — the codebase's single established pattern for LLM-stage tests.
- **Prior art:** the pitcher's existing suite (structure for the new stage's tests), the gate's suite (input migration), the writer's copied-from-pitch tests (the "code copies beat facts" idiom the relocation must keep satisfying).
- **Free end-to-end verify:** rerun the pitch-51 premise through slim pitcher → director-script stage → writer with zero credits; diff shipped scene lines against script beats. Story-fact survival (the bed/lift class) is the pass bar — the 07-15 PRD's own validation method, now spanning one more stage.

## Out of Scope

- Slice ② — splitting the writer's fused prompt into D1/D3 prompt files + envelope triage into config data. The writer's monolith prompt is untouched this slice.
- Slice ③ — asset stage (generate-auto/pick-human, persistent ref library).
- Slice ④ — executor probe ladder, watch-verdict labeling, envelope write-back ratification.
- Multi-generation splice lane (schema stays job-list-ready per the parent design; no splice code).
- Judge calibration / eval harness work (labels accumulate first).
- The latent voiceover path (07-15 PRD out-of-scope item stands; do not carry narration handling into the new stage unexamined).
- Pacing (no lever exists in the single-generation lane — do not judge this slice on it).

## Further Notes

- **Sequencing (user decision, overrode AI recommendation):** this restructure lands BEFORE the queued live generalization/taste render; that test then runs on the new architecture.
- **Knowledge routing rule for reviewers:** anything measured about the render model belongs in the envelope config, not in the new stage's prompt; anything per-story is injected per call and flushed. If a review finds a model-behavior fact written into the new prompt, that is a defect of this slice.
- **Seat-building conventions:** the new stage is an LLM seat; the repo's seat-engineering conventions (structured-output models, max_tokens trap, untrusted-data tagging, module-level prompt constants, tracing) apply to it like any other. Load the relevant project skill before building.
- **Process note (inherited, still true):** when this pipeline surprises you, read the Langfuse trace of the actual run before reasoning from code.
