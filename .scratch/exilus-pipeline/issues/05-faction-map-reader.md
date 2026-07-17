# 05: FactionMap schema + faction reader stage

Status: closed (shipped 2026-07-17 — commit 6e971e2, FactionReader emergent camps, 5-cap, budget-aware top-up, 706/706 tests green)

## Scope

Build the **Faction Map** artifact and the stage that produces it: a typed schema
(`FactionMap` + per-camp records) and a reader stage that replaces the single-consensus
`GapAnalysis` read **for the Exilus lane only**. Where the old `GapAgent` collapses a
whole thread into one `dominant_emotion` / `audience_want`, the faction reader must let
however many camps the audience actually contains emerge from the comments themselves,
then apply a cap of 5 as a post-generation filter (a single surviving camp is legal, not
an error). Each camp is an evidence-backed record — name, feeling, the audience's own
words for what they want, an explicitly-labeled INFERRED guess at the deeper desire
underneath that, verbatim evidence quotes carrying their upvote counts, and a weight
(share of surviving comments the camp represents).

The stage's input is the comment text the research stage already fetched (which already
passed the existing ≥5-upvote floor at the tool layer — see `reddit_search.py`'s
`_MIN_COMMENT_SCORE`). The common-case path spends nothing extra: no new Reddit call.
Only when the surviving-comment volume is short of a ~30-comment floor does the stage
make **at most one** additional scoped `reddit_search` top-up call; if the topped-up
volume is still short, the map is stamped THIN DATA rather than silently presented as
solid.

This ticket ALSO owns the FactionMap's persistence (coverage-audit assignment: no
other ticket owns it): a nullable JSON column + Alembic migration + write/read/replace
helpers, mirroring ticket 01's TopicBrief persistence pattern exactly (same table
decision — follow whatever table ticket 01's open question resolves to). Refresh
REPLACES the stored map, never stacks.

This ticket does NOT build: the Topic Brief/checker stage, the ideation stage, or the
fridge indexing/replace-on-refresh mechanics. The legacy single-consensus `gap_agent.py`
is untouched; Path A keeps using it.

## Existing code to read first

- `src/monitor/gap_agent.py` — the thing this stage's role replaces for this lane: shows
  the current single-consensus `GapAgent` shape (system prompt, `parse()` call with a
  per-caller `max_tokens` override, `@traced` wrapping, `ContextBundle` injection) that a
  faction reader is the multi-camp sibling of, not a mirror of — the camp-cap-as-post-filter
  and top-up/THIN-DATA control flow are new decisions this class never had to make.
- `src/monitor/schemas.py` — houses `GapAnalysis` (the single-consensus record this
  supersedes for the lane) and, more importantly, the `ScriptDraft`/`StoryScript` split
  (raw unconstrained LLM output vs. a code-composed, filtered final artifact) — the
  precedent shape for "let the LLM emit an unconstrained draft, then apply the cap in
  code afterward" that this ticket's camp-emergence-then-cap behavior needs to follow.
- `src/monitor/tools/reddit_search.py` — the tool the ~30-comment top-up call reuses:
  confirms the ≥5-upvote comment floor already lives here (`_MIN_COMMENT_SCORE = 5`),
  the `item_fetcher` test seam, the per-call Apify cost guard, and the upvote-tagged
  text shape (`[COMMENT | N upvotes] body`) evidence quotes must be pulled from.

## Decisions already locked (do not re-litigate)

- "Faction Map replaces the single-consensus gap analysis for this lane. Camp emergence
  is unconstrained during generation; a cap of 5 is applied afterward as a filter.
  Single camp legal. Camp record fields: name, feeling, surface_want (audience's words),
  deeper_desire (marked INFERRED), evidence quotes with upvote counts, weight (share of
  surviving comments). Built from comments already fetched during research (which
  already pass the ≥5-upvote floor at the tool layer); if surviving-comment volume is
  below floor (~30), at most ONE additional scoped Reddit call tops up; still short →
  THIN DATA stamp on the map." (Implementation Decisions)
- "The old single-consensus gap agent stays in place for the legacy lane until this lane
  proves out; Path A (subreddit scraper → event extractor → idea-fit gate) is sidelined
  for this lane, not deleted." (Implementation Decisions)
- "I want audience camps to emerge from the comments themselves rather than being forced
  into a preset count, so that the map reflects the thread, not the schema." (User Story 12)
- "I want at most 5 camps kept (filtered after emergence) and a single camp to be legal
  when the audience is unanimous, so that the map is honest in both directions." (User
  Story 13)
- "I want each camp to record feeling, surface want in the audience's own words, and the
  inferred deeper desire explicitly marked as inferred, so that I can distinguish what
  fans said from what Exilus guessed." (User Story 14)
- "I want each camp to carry evidence quotes with their upvote counts and a weight
  (share of surviving comments), so that I can judge how real and how big each camp is."
  (User Story 15)
- "I want the faction map built only from comments that survived the existing ≥5-upvote
  floor, so that zero-engagement comments never shape camps." (User Story 16)
- "I want the faction stage to reuse the comments research already fetched, topping up
  with at most one extra scoped Reddit call when volume is short, so that the common
  case costs nothing extra." (User Story 17)
- "I want a faction map built on too little data stamped THIN DATA, so that I know when
  camps stand on little evidence." (User Story 18)
- "I want the faction-map prompt validated once at build time by a shuffle-stability test
  (same camps from shuffled/subsampled comments), so that I know the instability that
  killed the old gap reads is actually fixed, not repainted." (User Story 24)
- Consult basis noted in the PRD: "Indi Young — emergent segmentation, surface-vs-interior
  wants, size as triage signal only; known depth ceiling of unprompted forum text
  accepted and documented, not papered over."
- "Depth ceiling accepted: unprompted forum text cannot reach interview-grade audience
  insight (no follow-up questions possible). deeper_desire is a best-effort inference,
  always labeled, never silently treated as fact." (Further Notes)
- Out of scope for this spec: "Runtime stability double-rolls of the faction read
  (build-time validation only)" and "Prompt-text ratification: system prompts are
  AI-drafted and user-ratified per repo convention, at implementation time."

## Acceptance criteria

1. A `FactionMap` (or equivalently-named) schema exists whose camp list holds at most 5
   camps regardless of how many the underlying LLM call emitted, and accepts a map with
   exactly 1 camp without error or padding.
2. Each camp record carries: `name`, `feeling`, `surface_want` (audience's own words),
   `deeper_desire` (present as a distinctly-labeled inferred field, never conflated with
   `surface_want`), one or more `evidence_quotes` each paired with its source upvote
   count, and a `weight` representing that camp's share of the surviving comments.
3. Given comment text whose surviving-comment count is at or above the ~30 floor, the
   stage produces a `FactionMap` making zero additional `reddit_search`/`item_fetcher`
   calls.
4. Given comment text below the ~30 floor, the stage makes exactly one additional
   scoped `reddit_search` top-up call before reading camps (never zero, never more than
   one, even if the topped-up volume is still short).
5. When surviving-comment volume remains below the ~30 floor after the (possible) one
   top-up, the returned `FactionMap` carries a THIN DATA stamp; when volume meets the
   floor (with or without a top-up), no such stamp is present.
6. The stage is callable end-to-end with an injected fake LLM and an injected
   `item_fetcher` fake — no live network call, no Apify spend, in the default test run.
7. `src/monitor/gap_agent.py`, `GapAnalysis`, and existing Path A tests are unmodified
   and continue to pass — this ticket adds a sibling stage, it does not touch the legacy
   single-consensus path.
8. Persisting a `FactionMap` for a topic and reading it back reconstructs an equal map
   (round-trip), following ticket 01's persistence pattern.
9. Persisting a second map for the same topic (the refresh path) REPLACES the stored
   value — nothing from the first write survives or merges in.

## Test notes

- Seams to use (all pre-existing patterns per the PRD's Testing Decisions — no new seam
  types): a fake/injected LLM standing in for the faction-reader's model call (same
  pattern `GapAgent`/`StoryCraftGate` tests already use); an injected `item_fetcher`
  fake for the top-up `reddit_search` call, so the volume-below-floor path never hits
  Apify in tests; an injected DB session for the persistence ACs (8-9), same fixture
  pattern ticket 01 uses.
- PRD-mandated behaviors this ticket's tests must cover explicitly (from Testing
  Decisions): "faction top-up triggers exactly once and only below floor"; "THIN DATA
  stamp"; "camp cap applied post-emergence"; "single-camp map accepted."
- Tests assert external artifact shape/content and control flow only (map shape, camp
  count, stamp presence, whether/how-many top-up calls fired) — never internal prompt
  wording or call order, per the PRD's stated testing philosophy.
- The shuffle-stability validation (User Story 24 / Testing Decisions: same camps
  re-emerge from shuffled/subsampled comments) is explicitly build-time, paid, manual,
  and NOT part of this ticket's CI test suite — it gates trusting the prompt in
  production, not this ticket's completion.
- Reuse `reddit_search.py`'s existing upvote-tagged text format
  (`[COMMENT | N upvotes] body`) as the source evidence quotes and their upvote counts
  are pulled from — do not invent a second tagging convention.

## Who types

Pure ops/boilerplate — AI-typed-by-default: any `providers.yaml` seat wiring the faction
reader needs (follows the existing `llm_for_seat()` convention) and, per the PRD's own
out-of-scope note, the first draft of the faction-reader's system prompt text (AI-drafted,
user-ratified before use). Everything else is decision-bearing and not a named-mirror of
an existing file (the camp-emergence-then-cap filter, the top-up-vs-THIN-DATA branch, the
~30-floor volume check, and the `FactionMap`/camp schema's fields and validators) — these
follow the repo's Gate model: user decides the control flow and edge-case handling before
any code is written (decide-before), AI may then type to that spec, and user traces the
top-up/THIN-DATA branches against edge cases afterward (predict-and-explain-after). AI
pairs on the schema/reader design and reviews; user implements per "Who writes what"
(algorithms and retrieval-adjacent logic are a pair item, not an AI-solo item).

## Open questions

- The PRD does not pin the exact interface between the research stage's output and this
  stage's input (e.g. whether the faction reader reads `ContextBundle.reaction_sample`
  directly, a fridge query result, or some other carrier of "comments already fetched")
  — left to implementation time.
- The PRD does not state whether camp `weight`s are required to sum to 1.0 across a map
  or are independently-computed per-camp shares; left to implementation time.
- (RESOLVED by coverage audit 2026-07-17: FactionMap persistence belongs to THIS
  ticket — column layout still an implementation-time decision, but ownership is
  settled. See Scope.)
- The PRD does not specify what happens to a camp's `evidence_quotes` when its
  underlying comments have no readable upvote count (the tool layer already falls back
  to a bare `[COMMENT]` tag in that case) — left to implementation time.
