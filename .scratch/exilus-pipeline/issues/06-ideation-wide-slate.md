# 06: Ideation stage — reshape the slim pitcher into a wide idea slate

Status: closed (shipped 2026-07-17 — commit 6e971e2, Ideator producing 8-15 idea slate with bounded coverage retry, 706/706 tests green)

## Scope

Reshape `StoryPitcher` (`src/monitor/story_pitcher.py`) from the current slim
pitcher — which reads a `TrendingEvent` + `GapAnalysis` and emits 2-3
`IdeaPitch` objects — into the PRD's third pinned stage: **Ideation**. The
stage's whole information diet becomes the two upstream pinned artifacts,
**Topic Brief** and **Faction Map**, and nothing else (no event, no gap
analysis, no raw research text) — every idea must be traceable to one of
those two inspectable artifacts. The slate widens from 2-3 to 8-15 one-line
ideas; every camp in the Faction Map must be the target of at least one idea,
with any remaining slots freely allocated across camps by the model's
judgment (no forced even split, no per-camp cap). Each idea in the slate
carries two tags: which camp it targets and which content mode it commits to.
The existing `IdeaPitch` pick-level fields (logline, mode, characters,
desired_moment, why_it_lands, legal_flag) are preserved as-is so nothing
downstream of the pick — StoryArchitect (D1), the craft gates, the writer —
needs to change. Re-rolling ("give me more ideas") re-runs only this stage
against the same pinned Topic Brief + Faction Map, with the prior run's
loglines supplied back to the model as an explicit do-not-repeat list — no
re-research, no re-faction-read, near-zero cost.

This ticket covers the pitcher class, its prompt, and the `IdeaPitch` /
`IdeaPitchSlate` schema changes needed to carry the camp/mode tags and the
larger slate bound. It does NOT cover building the `TopicBrief` or
`FactionMap` schemas themselves (those are sibling tickets in this same PRD
sequence — this ticket only consumes them as already-defined typed objects,
mirroring how the current `pitch()` accepts already-loaded `TrendingEvent` /
`GapAnalysis` objects rather than IDs). It does NOT cover persistence/loading
of the pinned artifacts from the DB, or the driver that wires
research → faction → ideation together — see Open Questions.

## Existing code to read first

- `src/monitor/story_pitcher.py` — the file being reshaped. Current
  `pitch(event, gap, bundle)` signature, `STORY_SYSTEM_PROMPT` /
  `_IDEA_FIELD_SPEC` (hardcode "2-3 distinct story ideas" and ground craft
  rules in `gap.audience_want` / `gap.dominant_emotion` — both need rewriting
  against Faction Map fields instead), and `_warn_if_low_diversity` (the
  non-gating pairwise-cosine check — reusable as-is over a bigger slate).
- `src/monitor/schemas.py` — `IdeaPitch` (the pick-level contract that must
  stay byte-compatible in its existing fields) and `IdeaPitchSlate`
  (`Field(min_length=2, max_length=3)` — the bound this ticket changes to
  8-15). Also where `TopicBrief` / `FactionMap` / `Camp` will live once their
  sibling tickets land — this ticket's `pitch()` signature depends on those
  types existing.
- `src/monitor/prompt_blocks.py` — the shared tagged-block rendering pattern
  (`event_block` / `gap_block`) that keeps two stages from drifting on tag
  format. This ticket adds the equivalent `brief_block` / `faction_block`
  renderers here, not inline in the pitcher, following the existing
  precedent.

## Decisions already locked (do not re-litigate)

- "Ideation stage reshapes the existing slim pitcher: input becomes the two
  artifacts (not event + gap), slate grows from 2-3 to 8-15 one-line ideas,
  every camp covered at least once, remaining allocation free; each idea
  tagged with target camp + mode. Idea record keeps the existing pick-level
  contract so the downstream director (StoryArchitect D1), craft gates, and
  writer are untouched." (Implementation Decisions)
- "Re-rolls: same pinned inputs, prior loglines passed as do-not-repeat."
  (Implementation Decisions; User Story 21: "idea re-rolls to reuse the
  pinned artifacts and be shown prior ideas with an instruction not to repeat
  them, so that 'more ideas' is cheap and fresh.")
- "I want ideation to read ONLY the pinned brief and map, so that every idea
  is traceable to an artifact I can inspect — no hidden context." (User
  Story 19)
- "I want a slate of 8-15 one-line ideas with every camp represented at
  least once and each idea tagged with its target camp and mode, so that I
  can skim the whole landscape and pick with my own taste." (User Story 20)
- "I want my picked idea to hand off in the existing pick-level contract, so
  that the downstream director, gates, and writer keep working unchanged."
  (User Story 23)
- "Pinning semantics: artifacts and fridge contents are per-topic facts,
  written once; idea re-rolls never re-run research or faction reading;
  explicit refresh re-runs everything and replaces stored state."
  (Implementation Decisions)
- Testing Decisions, specific mandated behaviors for this stage: "slate
  covers every camp; re-roll excludes shown ideas; pick hands off in the
  existing contract."
- Out of Scope: "Everything downstream of the pick: StoryArchitect (D1),
  craft gates, writer, render executor, and all render-lane decisions
  (explicit user instruction: 'forget everything about rendering for
  now')."
- Out of Scope: "Prompt-text ratification: system prompts are AI-drafted and
  user-ratified per repo convention, at implementation time, not in this
  spec."

## Acceptance criteria

1. The pitcher's stage-entry method accepts a `TopicBrief` and a
   `FactionMap` as its inputs — no `TrendingEvent` or `GapAnalysis` parameter
   remains on the call.
2. For any valid `FactionMap` (1 to 5 camps), the returned `IdeaPitchSlate`
   contains between 8 and 15 `IdeaPitch` entries inclusive, enforced by a
   schema field bound (the existing `min_length`/`max_length` pattern, wider
   numbers).
3. Every camp present in the input `FactionMap` is the target of at least
   one idea in the returned slate (coverage is externally checkable by
   comparing the set of idea target-camp tags against the set of camp
   names/ids in the map).
4. Ideas beyond the one-per-camp floor are not forced into an even split or
   a per-camp cap — a test with more slate slots than camps must not fail
   when allocation is uneven across camps.
5. Every `IdeaPitch` in the slate carries a field identifying its target
   camp and a field identifying its mode; neither is ever missing.
6. `IdeaPitch`'s pre-existing fields (`logline`, `mode`, `characters`,
   `desired_moment`, `why_it_lands`, `legal_flag`) are unchanged in name and
   type from the current schema — grep-confirmed that no call site in
   `src/generation/story_architect.py`, the craft gate, or the writer
   requires modification because of this ticket.
7. A re-roll call takes the same pinned `TopicBrief`/`FactionMap` plus a list
   of prior loglines, and those prior loglines are passed into the LLM call
   as do-not-repeat material (observable at the call-arguments level — see
   Test notes; see Open Questions for whether repeats are also filtered in
   code).
8. [Depends on the Open Questions answer for the dedup mechanism] Either:
   (a) if dedup is prompt-only, a test confirms the prior loglines reach the
   LLM call as do-not-repeat input — repeat avoidance itself is the model's
   job, not asserted on output; or (b) if dedup is also code-enforced, a
   fake-LLM test returning a canned duplicate confirms it is filtered from
   the returned slate. Do not assert both until the mechanism is decided.
9. The stage-entry method's signature (AC #1: only `TopicBrief` +
   `FactionMap` in) is itself the external proof that no event/gap material
   can reach the call — no separate assertion on prompt string contents is
   required or expected (see Test notes).
10. The existing non-gating diversity check still runs over the widened
    8-15-idea slate without raising or blocking the call.

## Test notes

- Fake LLM per the repo's existing monitor-agent test pattern (canned
  `IdeaPitchSlate` responses) — no network, no live model call.
- Canned `TopicBrief` / `FactionMap` fixtures stand in for the upstream
  pinned artifacts; this ticket does not need an injected DB session or a
  fake `item_fetcher` since the pitcher, like today, takes already-loaded
  typed objects rather than performing its own fetch/persistence.
- PRD-mandated behaviors this ticket must cover, from Testing Decisions:
  slate covers every camp; re-roll excludes shown ideas; pick hands off in
  the existing contract (i.e. a test that feeds a picked `IdeaPitch` into
  the existing StoryArchitect/gate call shape unchanged).
- Tests assert external behavior only (artifact shape/content, coverage,
  dedup-on-re-roll) — never internal prompt wording or call order, per the
  PRD's Testing Decisions. Draw the line at *prompt composition* vs.
  *prompt wording*: which artifacts/values were handed into the LLM call
  (fair game — inspect the fake LLM's recorded call arguments, e.g. "prior
  loglines were passed in") is external behavior; the exact sentences of the
  rendered prompt string are not asserted on.
- The diversity-check test should cover the larger slate size (8-15) to
  confirm the pairwise-cosine computation doesn't choke or slow
  unacceptably at the new scale.
- Out of scope for this ticket's tests: the top-seam pipeline-driver wire
  test (topic in → slate out across all three stages) belongs to whichever
  ticket wires research → faction → ideation together.

## Who types

All of this ticket is decision-bearing (prompt redesign grounded in new
artifacts, schema shape for camp/mode tagging, free-allocation-with-floor
coverage logic, re-roll dedup wiring) — user-implements per the repo's gate
model (decide-before: state the coverage/allocation approach and the
target-camp field shape before writing; predict-and-explain-after on the
re-roll dedup test). The one named exception per repo convention: prompt
COPY (the rewritten system prompt / field spec text) is AI-drafted, then
user-ratified before it ships — the PRD calls this out explicitly as
deferred-to-implementation-time, not decided in this ticket. No pure-ops
sub-parts (no migration, no providers.yaml seat wiring) were identified in
this ticket's scope.

## Open questions

- PRD does not name the exact field(s) `IdeaPitch` should carry for the
  target-camp tag (e.g. a string referencing `Camp.name`, vs. an id/enum) —
  left as an implementation-time schema decision.
- PRD does not state whether this ticket owns loading the pinned
  `TopicBrief`/`FactionMap` from persistence, or whether it only accepts
  them as already-loaded objects passed in by a driver (the pattern this
  ticket assumes, mirroring today's `pitch(event, gap)` shape). Confirm
  before implementation.
- PRD's Further Notes say "module naming at implementation time follows
  existing repo conventions" — whether `StoryPitcher`/`story_pitcher.py` get
  renamed for the ideation stage is not decided here.
- PRD does not specify a new similarity threshold or behavior change for the
  diversity check at 8-15 ideas versus 2-3 — assumed unchanged unless
  measurement says otherwise.
- Ordering/dependency on the sibling tickets that define `TopicBrief`,
  `FactionMap`, and `Camp` is assumed but not itself specified by the PRD as
  a ticket sequence — confirm those schemas are the ones this ticket should
  import.
- The PRD says re-roll do-not-repeat is "prior loglines passed as
  do-not-repeat" / "an instruction not to repeat them" (US21) — a prompt
  instruction to the model. It does not say whether the returned slate is
  ALSO code-filtered against the prior loglines (defense against the model
  ignoring the instruction). This decides how AC #8 is written and tested
  (call-arguments check only, vs. an output-filter test with a canned
  duplicate) — confirm which before implementation.

## Comments
