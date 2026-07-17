# 02: Research loop's finalize step synthesizes a Topic Brief

Status: closed (shipped 2026-07-17 — commit 6e971e2, ContextAgent.gather_brief() with budget-carrying re-entry, 706/706 tests green)

## Scope

Extend the existing LangGraph context agent (`src/monitor/context_agent.py`) so its
`finalize` node synthesizes a **Topic Brief** — the PRD's five "can-explain" fields, each
citing sources drawn from the URLs the run actually gathered — instead of, or alongside,
the current `ContextSynthesis` (summary/key_moments/unresolved_facts).

This ticket is synthesis only. It does NOT build:
- the two-layer checker (code checks + cross-family LLM judge) or its 2-round repair loop,
  UNVERIFIED stamping, or the operator halt — that grades the brief this ticket produces,
  and is a separate ticket;
- the per-topic fridge indexing/replace-on-refresh behavior;
- the Faction Map or Ideation stages;
- DB persistence of the brief (JSON column + migration) — this ticket's job ends at
  `ContextAgent` returning an in-memory brief object, the same boundary `run()`/`gather()`
  already draw for `ContextBundle` today.

The loop's shape is explicitly unchanged: same plan/act nodes (`reddit_search`,
`tavily_search`, `firecrawl_extract`), same `decide_next_step` routing, same caps (20 tool
calls, $1.00 Apify per run, 3-consecutive-stale-reddit-calls guard, reaction+context floor).
Only the `finalize` node's output — and the schema/prompt behind it — changes.

One addition beyond finalize (coverage-audit assignment 2026-07-17: no other ticket
owned it): this ticket ALSO builds the loop's **re-entry interface** — the checker's
repair rounds (ticket 03) must be able to re-enter the loop with a targeted follow-up
query while CARRYING the original run's remaining caps (tool calls, Apify spend, stale
streak count cumulatively across the initial run and up to 2 repair passes — never a
fresh budget per pass). This ticket owns the interface and the budget threading; ticket
03 owns when and with what query it gets called.

## Existing code to read first

- `src/monitor/context_agent.py` — the whole LangGraph loop this ticket extends. Read
  `_finalize` (the node being changed), `FINALIZE_SYSTEM_PROMPT` (the prompt being
  replaced or supplemented), `build_context_bundle` (assembles the artifact from state
  today — the new brief needs an equivalent assembly step), and `run()`/`gather()` (the
  public entry points whose return shape may need a new member).
- `src/monitor/tools/reddit_search.py` — shows where `state.urls` entries actually come
  from (`ToolResult.urls`, one per matched post) and how upvote-tagged text is threaded
  into `reddit_text`. Relevant because the brief's citations must be drawn from exactly
  this gathered URL set, not invented — read it to know what a "real, gathered URL" looks
  like and how it's already threaded through `_act_reddit`/`_act_tavily`.
- `src/monitor/schemas.py` — where `ContextSynthesis`, `ContextBundle`, and `PlanDecision`
  are defined today; the new `TopicBrief` (or equivalent) schema is a sibling of these and
  follows the same `BaseModel`/`ConfigDict(extra="forbid")` convention every LLM response
  model in this file already uses.

## Decisions already locked (do not re-litigate)

- "Research stage extends the existing context-gathering loop (LangGraph plan/act loop,
  Reddit + Tavily + Firecrawl tools, community lookup). Existing caps unchanged: 20 tool
  calls, $1.00 Apify per run, 3-stale-Reddit-calls saturation guard, reaction+context
  floor."
- "Topic Brief schema: five fields — identity, recent events, key characters and
  relationships, why people care, open unknowns — each with source citations. Open
  unknowns carries forward the existing unresolved-facts concept. No wave_status field
  (user decision). No visual/lore-dump fields (belong downstream)."
- "I want the Topic Brief to answer five fixed questions (what is this; what recently
  happened; key characters + relationships; why people care; open unknowns), so that I
  can trust one consistent research contract per topic." (User Story 3)
- "I want every brief field to cite the source it came from, so that I can verify any
  claim instead of trusting the model's memory." (User Story 4)
- "I want research to proceed regardless of whether the topic has a live reaction wave, so
  that quiet/evergreen topics still produce content ideas." (User Story 2 — the loop this
  ticket feeds already has no freshness requirement; don't add one here.)
- Checker, repair loop, and UNVERIFIED-halt are real PRD requirements but grade the brief
  this ticket produces — they belong to a separate ticket, not this slice.
- "Prompt-text ratification: system prompts are AI-drafted and user-ratified per repo
  convention, at implementation time, not in this spec." (Out of Scope)
- "Persistence: artifacts stored as JSON columns on the topic's event/topic record,
  following the existing idea_json/story_json precedent; exact column layout decided at
  implementation time via migration." — not this ticket's job.
- Testing: "Tests assert external behavior only: given canned inputs, the stage produces
  the right artifact shape/content and the right control flow ... never internal call
  order or prompt wording." Seam: "fake/injected LLM per stage (research planner,
  checker, faction reader, ideator) — the pattern every monitor-agent test already uses."

## Acceptance criteria

1. Running the context-gathering graph (with an injected fake LLM standing in for the
   finalize call) produces a brief artifact carrying exactly five fields corresponding to:
   identity, recent events, key characters and relationships, why people care, and open
   unknowns.
2. The identity, recent events, key-characters-and-relationships, and why-people-care
   fields each carry at least one citation.
3. No `wave_status` field exists anywhere on the new artifact.
4. No visual-description or lore-dump field exists anywhere on the new artifact.
5. The prompt/user-message the finalize node sends to the LLM includes the full set of
   URLs gathered during the run (`state.urls`) as the citable source list — the same
   grounding discipline `_plan`'s prompt already applies to `reddit_gathered`/
   `web_gathered` (assert on what's passed to the fake LLM, not on internal call order).
6. The existing loop caps and routing are unaffected: a canned run that previously hit the
   20-tool-call ceiling, the $1.00 Apify ceiling, the 3-stale-reddit-call guard, or the
   reaction+context floor in `decide_next_step` behaves identically before and after this
   change (same node reached, same call counts).
7. Whichever resolution is chosen for the ContextSynthesis/ContextBundle question (see
   Open Questions), any existing caller that depends on `ContextBundle`/`to_context_block()`
   for the legacy lane still gets a valid `ContextBundle` back — no silent break of
   `GapAgent`/`StoryPitcher`'s existing context-injection path.
8. Re-entering the loop with a follow-up query after an initial run continues within the
   REMAINING budget: with an initial run that consumed N tool calls, a re-entry pass can
   consume at most (20 - N) more before `decide_next_step` stops it; the same cumulative
   carry holds for the Apify cost cap. Observable with injected fakes: total calls across
   initial + re-entry passes never exceed the single-run ceiling.

## Test notes

- Seam: fake/injected LLM for the finalize node — the same pattern
  `test_pitch_grounding.py`/existing `context_agent` tests already use for `_plan`, applied
  to whatever call(s) `_finalize` now makes.
- Seam: injected `item_fetcher` fakes for `reddit_search`/`tavily_search`/
  `firecrawl_extract` when exercising a full `run()`/`gather()` pass end to end — no
  network, no Apify spend, mirrors the existing wire-test convention.
- Must cover: the five-field shape and per-field citation presence (AC1-2); absence of
  `wave_status` and visual/lore fields as an explicit regression guard against a decision
  the PRD already rejected (AC3-4); the finalize prompt is grounded on `state.urls`, not
  just on the raw text blobs (AC5); every existing cap/routing test in
  `tests/monitor/` that exercises `decide_next_step`/the loop continues to pass unchanged,
  proving the loop itself wasn't touched (AC6).
- Driver-level: a context-agent-only wire test (topic in → brief out, all fakes injected)
  is in scope here; the full Exilus pipeline driver (brief → faction map → slate) is a
  later ticket's job once those stages exist.
- Prior art: existing `context_agent` tests already fake the LLM for `_plan`/`_finalize`
  and inject `item_fetcher` for the tool nodes — extend that harness rather than building a
  new one.

## Who types

Decision-bearing throughout (new schema fields and citation shape, prompt design, node
wiring, test design) — user-implemented per the repo's teaching model; the gate model
applies (decide the schema/citation shape and prompt approach before writing code, then
predict/trace the finalize node's behavior against a canned run). The one carve-out: the
system prompt's exact wording is AI-drafted and user-ratified per the repo's existing
convention (an explicit PRD Out-of-Scope item), not hand-typed by the user. No pure-ops
sub-parts (no migration, no `providers.yaml` seat wiring) fall inside this ticket's scope.

## Open questions

- The task framing for this ticket says the brief comes "instead of/alongside" the current
  `ContextSynthesis` — the PRD never resolves this. The PRD does say the old
  single-consensus gap agent and Path A stay in place "until this lane proves out," which
  implies *something* must keep the legacy `ContextBundle`/`to_context_block()` path
  working for `GapAgent`/`StoryPitcher`, but it never states whether one `finalize` run
  should produce both artifacts, whether `ContextSynthesis` is dropped entirely, or whether
  the legacy lane keeps a separate, untouched code path. Needs a decision before coding.
- The `TopicBrief` Pydantic shape (field names, citation container, UNVERIFIED
  representation, open_unknowns citation question) is TICKET 01's to decide — this ticket
  consumes whatever ticket 01 defines and must not fork a divergent shape. (Coverage-audit
  clarification 2026-07-17: 01 is the schema authority; the same open questions listed
  there are answered once, in 01, not re-decided here.)
- Whether the brief is a new member of `ContextBundle` or a wholly separate return value
  from `ContextAgent.run()`/`gather()` is not specified.
