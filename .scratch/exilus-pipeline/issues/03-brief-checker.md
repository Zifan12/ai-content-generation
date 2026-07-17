# 03: Topic Brief checker — two-layer grading + bounded repair loop

Status: ready-for-human

## Scope

Exilus's research stage produces a pinned Topic Brief (five fields, each carrying
source citations). This ticket builds the gate that decides whether that brief is
good enough to pin as-is, or needs another pass of research before it does.

The checker is two layers, run in order, and never lets the thing that authored the
brief grade its own work:

1. **Code checks** — pure, deterministic, no LLM: every one of the five brief
   fields is non-empty, and every citation it carries resolves to a URL that is
   actually in the set of URLs this run gathered (not a hallucinated or
   remembered-from-training URL).
2. **LLM specificity judge** — one cheap, cross-family LLM call (the repo's
   existing judge-seat convention: a different model family from whatever
   produced the brief content) judging each field for per-field specificity —
   is this field's content concrete and about THIS topic, or generic filler that
   would pass for any topic in the niche.

A brief with any failing field (from either layer) does not stop the run — it
triggers a repair round: each failing field's gap becomes the next research
query, fed back into the existing research loop, after which the brief is
rebuilt and the two layers run again. This can happen at most twice. If fields
are still failing when that budget is spent, the brief is persisted anyway with
UNVERIFIED stamps on exactly the fields that never passed, and the run halts —
control returns to the operator instead of silently shipping a bad brief
downstream. A brief that passes (immediately, or after 1-2 repair rounds) flows
onward with no blocking human-approval step.

This ticket owns: the two check layers, the verdict schema(s), the repair-round
orchestration and its 2-round bound, the gap-to-next-research-query handoff
contract (shape only — see Open Questions for what's undecided), and the
terminal persist+halt vs. flow-on branching. It does NOT own: the Topic Brief
schema (ticket 01), the research stage that produces brief field content
(ticket 02), the budget-carrying loop re-entry interface the repair rounds
call (ticket 02 builds it — coverage-audit assignment 2026-07-17; this ticket
CONSUMES it with the failed field's gap as the follow-up query), the Faction
Map, ideation, or anything downstream of the pick (all explicitly out of
scope in the PRD).

## Existing code to read first

- `src/monitor/context_agent.py` — the existing capped research loop (plan/act/
  judge/stop LangGraph agent) this checker's repair rounds feed back into. Read
  for: the `_DEFAULT_MAX_TOOL_CALLS` / `_DEFAULT_MAX_RUN_APIFY_COST` /
  `_DEFAULT_MAX_CONSECUTIVE_STALE_REDDIT_CALLS` caps (unchanged per PRD — a
  repair round runs inside this same budget, it does not get a fresh one), and
  the `ContextBundle.references`/`state.urls` shape — the "actually-gathered
  URL set" the code-check layer's citation check compares against.
- `config/providers.yaml` — the `llm:` seat registry. This ticket adds one new
  seat (the specificity-judge call) here; read the file's own docstring on the
  cross-family / promotion-protocol convention before picking a model, and note
  the existing `groundedness_judge` and `eval_judge` seats as the concrete
  precedent for "cheap, cross-family from what it's judging."
- `src/providers/llm/factory.py` — `llm_for_seat()`, the only sanctioned way a
  new seat gets constructed (fail-loud on unknown seat / missing config /
  missing API key). The checker's LLM is constructor-injected via this
  function in production, exactly like every other monitor-agent class.
- `src/monitor/story_craft_gate.py` — the closest existing precedent for
  "LLM judge produces a per-dimension verdict, a derived pass/fail rolls it up,
  a bounded repair re-runs the producer on failure notes." Read for the
  verdict-schema shape (dimensions judged, then a summary field) and for how
  `scripts/pitch_angles.py` wires ONE bounded repair around it today — this
  ticket's 2-round bound is the same pattern, just with a different round count
  and a repair target (research, not the script author).
- `src/evals/groundedness_check.py` and `src/monitor/pitch_grounding.py` (read
  during orientation, not in the assigned list, but directly on point) — the
  two existing "cheap cross-family LLM checker" implementations in this repo.
  Both show the pattern this ticket's specificity judge should follow:
  chain-of-thought (`reasoning`) emitted before any label, a derived
  boolean/verdict field (`@computed_field`) rather than an LLM-set one so the
  verdict can never contradict its own evidence list, and untrusted-data
  tagging (`<pitch>`, `<canon>` blocks) for anything the LLM reads that isn't
  the system prompt itself.

## Decisions already locked (do not re-litigate)

Pulled from the PRD (`.scratch/exilus-pipeline/PRD.md`):

- "Checker is two-layer and never self-graded: (1) code checks — field
  non-empty, citation present and drawn from the actually-gathered URL set;
  (2) one cheap cross-family LLM call judging per-field specificity (repo's
  existing judge-seat convention). Max 2 fail-and-repair rounds; each failed
  field's gap becomes the next research query. On exhaustion: brief persisted
  with UNVERIFIED stamps, run halts for the operator. Passing brief: no
  blocking gate."
- "Never self-graded" / "cross-family" is itself the locked constraint, not an
  implementation detail — the specificity-judge seat must be a different model
  family from whatever seat authors the Topic Brief's field content. The exact
  model choice is ops (providers.yaml), but a same-family checker would violate
  this lock.
- Topic Brief schema (context for what the checker grades, not this ticket's to
  build): five fields — identity, recent events, key characters and
  relationships, why people care, open unknowns — each with source citations.
  Open unknowns carries forward the existing unresolved-facts concept. No
  wave_status field. No visual/lore-dump fields.
- "Research stage extends the existing context-gathering loop... Existing caps
  unchanged: 20 tool calls, $1.00 Apify per run, 3-stale-Reddit-calls saturation
  guard, reaction+context floor." A repair round's research runs inside this
  same, already-enforced run-level budget — it is not a second, independent
  allowance.
- "I want research bounded by the existing caps..., so that a thin topic cannot
  loop forever or burn budget silently" (User Story 7) and "I want a brief that
  still fails after the caps to be written anyway with failing fields stamped
  UNVERIFIED and the run halted for me... never a silent proceed on bad
  research" (User Story 8).
- "I want a failed brief field to send its gap back into the research loop as
  the next query (max 2 repair rounds), so that the loop converges instead of
  retrying blindly" (User Story 6).
- "I want a passing brief to flow onward with no mandatory approval click, so
  that clean runs have no friction" (User Story 9).
- Out of scope note: "Cost/model seat changes beyond adding the checker seat
  (seat wiring follows the existing providers.yaml convention)" — this ticket
  is explicitly the one adding that one new seat.
- Out of scope note: "Prompt-text ratification: system prompts are AI-drafted
  and user-ratified per repo convention, at implementation time, not in this
  spec" — the specificity judge's system prompt is drafted, then ratified, at
  implementation time; it is not decided in the PRD or this ticket.
- Out of scope note: "Persistence: artifacts stored as JSON columns on the
  topic's event/topic record... exact column layout decided at implementation
  time via migration" — the checker triggers a persist call (with an injected
  DB session) on the UNVERIFIED-exhaustion path, but the column/table shape
  itself is an implementation-time migration decision, not this ticket's to
  make.

## Acceptance criteria

1. Given a Topic Brief where all five fields are non-empty and every citation
   they carry is a URL present in the run's gathered URL set, the code-check
   layer reports every field passing, with no LLM call made for this layer.
2. Given a Topic Brief with at least one empty field, the code-check layer
   flags that specific field as failing, independent of what the LLM
   specificity judge would say about it.
3. Given a Topic Brief where a field's citation is a URL that is NOT in the
   run's gathered URL set, the code-check layer flags that field as failing —
   a citation must be drawn from what was actually gathered, not merely
   present as a string.
4. Given a Topic Brief that passes every code check, the LLM specificity judge
   still runs and can independently fail a field it judges generic/non-specific
   to this topic — a field can pass layer 1 and still fail the brief overall
   via layer 2.
5. A brief where both layers pass every field is stamped with no UNVERIFIED
   markers anywhere and flows onward with no blocking human-approval step (no
   halt, no gate call requiring operator input).
6. A brief with one or more failing fields (either layer) triggers a repair
   round rather than an immediate halt: a failing field causes a subsequent
   research query targeting that field's specific gap (empty / uncited /
   judged-too-generic), fed back into the research loop, after which the
   brief is rebuilt and re-checked.
7. The repair loop runs at most 2 rounds total — a brief still failing after 2
   repair rounds stops repairing (does not attempt a 3rd), regardless of
   whether any individual field improved along the way.
8. A field that fails in round 1 but is fixed by round 1's repair (the
   injected fake research callback supplies a satisfying citation / more
   specific content) passes on the round-2 check and carries no UNVERIFIED
   stamp in the final persisted brief.
9. After the 2-round repair budget is exhausted with one or more fields still
   failing, the brief is persisted with an UNVERIFIED stamp on exactly the
   fields still failing (not on fields that passed), and the run halts —
   observable as a distinct halt outcome the driver surfaces to the operator,
   not a silent pass-through.
10. The existing research-loop caps (max tool calls, max run Apify cost,
    consecutive-stale-reddit-calls guard) remain in force during repair-round
    research calls — a repair round is not exempt from them and does not reset
    them to a fresh budget.

## Test notes

Per the PRD's Testing Decisions, tests assert external behavior only (artifact
shape/content and control flow — halt, repair, stamp — never internal call
order or prompt wording). The PRD names exactly three must-have behaviors for
this checker; each maps to a seam:

- **"Checker fails a citation-less field"** — construct a Topic Brief with one
  field missing a citation (or citing a URL outside the gathered set) and
  assert the code-check layer flags exactly that field, using a fake/injected
  specificity-judge LLM that is never even called for this case (or, if the
  design runs both layers unconditionally, assert its verdict is irrelevant to
  the failure) — no real LLM, no network.
- **"Checker repair loop respects the 2-round bound"** — inject a fake
  research callback that never resolves the gap (every repair round returns
  content that still fails), and assert the loop stops after exactly 2 repair
  rounds — no 3rd round attempted, no infinite loop. This is the seam-critical
  test: the fake research callback must be injectable exactly like
  `context_agent.py`'s existing fake-fetcher-item tests (no real
  reddit_search/tavily_search/firecrawl_extract call), so the bound is provable
  without network or spend.
- **"UNVERIFIED + halt path"** — drive a brief through 2 exhausted repair
  rounds (fake research callback + fake specificity-judge LLM, both rigged to
  keep failing the same field) and assert the persisted brief carries the
  UNVERIFIED stamp on that field only, via an injected DB session (no real
  Postgres), and that the driver-level return/signal is the halt outcome, not
  the flow-on outcome.

Additional seams already established elsewhere in the codebase to reuse, not
reinvent: fake/injected LLM per stage (the pattern every monitor-agent test —
`test_story_pitcher.py`, `test_pitch_grounding.py`, etc. — already uses) for
the specificity judge; an injected DB session for the persistence call, same
as the fridge/artifact tests; the top-level pipeline-driver wire test pattern
(topic in -> slate out with all fakes injected) if this ticket's checker gets
exercised end-to-end as part of that driver test rather than only in
isolation.

Do not fold in tests for fridge refresh, faction top-up/THIN DATA, camp
cap/single-camp, slate coverage, re-roll dedup, or pick handoff — those are
PRD-mandated behaviors for other stages, not this checker.

## Who types

Per the repo's teaching model: providers.yaml's new checker-seat entry and any
Alembic migration needed for the UNVERIFIED-stamp/persisted-brief column shape
are pure ops/config boilerplate and AI-typed-by-default (must still satisfy
the cross-family lock above when the model is picked); the checker's verdict
schema(s), the citation-against-gathered-URL-set predicate, the repair-round
orchestration and its 2-round bound, the gap-to-query handoff, and the
persist-vs-flow-on branching are decision-bearing business logic and are
user-implemented under the standard gate model (user decides the control flow
and interfaces before anything is written; AI may implement to that spec and
reviews/predicts after) — the LLM specificity judge's system-prompt text is
AI-drafted and user-ratified per the repo's existing convention, same as every
other prompt in this codebase.

## Open questions

PRD is silent on the following; do not decide these here — surface to the
user at implementation time:

- Exact Pydantic shape of the Topic Brief and its per-field citations (one
  citation per field vs. a list; a `Citation` sub-model vs. a bare URL string)
  is not specified by the PRD and is not this ticket's to invent — this
  checker consumes whatever shape the research-stage ticket defines. If that
  shape does not yet exist when this ticket starts, its definition is a
  cross-ticket dependency, not a decision this ticket makes unilaterally.
- The exact mechanism by which "a failing field's gap becomes the next
  research query" is not specified: is the query the failure reason text
  reused verbatim, or a separate reformulation step; and when multiple fields
  fail in the same round, is it one combined research call covering all gaps,
  or one call per failing field? The PRD only locks the outcome (gap -> next
  query), not the mechanism.
- Precedence between the existing research-loop caps and the 2-round repair
  bound is not fully specified: if a per-run cap (tool calls / Apify cost /
  stale-streak) is hit mid-repair, before the 2-round budget itself is spent,
  does that route to the same UNVERIFIED+halt outcome as bound-exhaustion, or
  a distinct one? The PRD locks that caps remain in force and that the run
  never proceeds silently on bad research, but not this specific precedence.
- Whether the specificity judge runs once over all five fields in a single
  call, or once per field, is unspecified — either satisfies "one cheap
  cross-family LLM call" loosely, but the PRD doesn't pin the call shape.
