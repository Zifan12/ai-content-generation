# 07: Pipeline driver and pinning

Status: ready-for-human

## Scope

This ticket builds the Exilus top-level driver: the topic-in → slate-out
orchestrator that strings research → checker (+ bounded repair) → faction
read → ideation together, exactly the role `run_pitch_pipeline` plays for the
legacy Path A/B monitor chain. It owns the CONTROL FLOW between stages, not
the stages themselves:

- Deciding, per invocation, whether to run research/checker/faction fresh or
  skip straight to ideation on the pinned Topic Brief + Faction Map (plain
  idea re-roll), or force everything to re-run and replace stored state
  (`--refresh`).
- Running the checker's fail-and-repair loop against the research stage (max
  2 rounds) and, on exhaustion, persisting the brief with its UNVERIFIED
  stamps and halting for the operator instead of continuing to faction read.
- On a passing brief, proceeding through faction read and ideation with no
  blocking approval prompt.
- On a re-roll, passing previously-shown idea loglines into ideation as
  do-not-repeat context.
- Printing the resulting slate, taking the operator's pick, and persisting +
  handing off that pick in the existing pick-level record/JSON contract so
  downstream tooling built for Path A/B keeps working unchanged.

Out of this ticket's scope: the TopicBrief schema/persistence (ticket 01),
the research-loop extension and the two-layer checker's own pass/fail logic,
the faction-map reader (emergence, camp cap, THIN DATA, top-up), and the
ideation stage's own slate-generation logic (camp coverage, mode variety).
Those are separate tickets; this one calls into them as injected components,
the same way `run_pitch_pipeline` takes `idea_fit_gate`/`gap_agent`/
`story_pitcher` as arguments rather than implementing them inline.

Also out of scope, per the PRD: everything downstream of the operator's
pick (StoryArchitect/D1, craft gates, writer, render executor). Whether this
driver inlines a call into that existing (unchanged) tail the way
`run_pitch_pipeline` does today, or stops at writing the approved record +
handoff JSON for a separate existing entry point to pick up, is not decided
by the PRD — see Open questions.

**Prerequisite carried from the PRD's Further Notes:** the ~40-file
uncommitted staged-director slice ① working tree must be committed before
this ticket starts — the driver sits directly on top of that slice's pitcher/
gate shape.

## Existing code to read first

- `scripts/pitch_angles.py` (`run_pitch_pipeline`) — the DI-style orchestrator
  pattern this driver mirrors: every stage injected as a plain argument, a
  numbered-slate printer, a `choice_provider` seam for the operator's pick,
  and a persist-then-write-handoff-JSON shape at the end. This ticket's
  driver is the same shape of function, wired to Exilus's four stages
  instead of scraper/gate/gap/pitcher.
- `scripts/repitch_event.py` — the PINNING precedent this ticket generalizes:
  `load_pinned_gap` + `_PinnedGapAgent` reuse a stored per-event read instead
  of re-analyzing, and `_OneEventScraper`/`_IdentityExtractor` show the
  fake-injection-for-reuse pattern. Exilus's "skip research/checker/faction
  on a plain re-roll" behavior is this same idea spanning more stages.
- `tests/monitor/test_pitch_angles.py` — the existing "wire test": the whole
  pipeline driven end-to-end with fakes for every component, asserting call
  counts/order on the fakes plus persisted-row and handoff-JSON shape. This
  ticket's own driver test should mirror this style (see Test notes).
- `src/monitor/fridge.py` (`index_web_text`) — documents its own current
  limitation directly relevant here: "Not idempotent: calling twice for the
  same topic inserts duplicate rows (v1 is within-run, called once per run)."
  The driver's `--refresh` path must trigger delete-then-write, not repeat
  this duplicate-on-reindex behavior — whether the delete lives in this
  ticket's driver call or inside the fridge module itself is an open question.
- `.scratch/exilus-pipeline/issues/01-topic-brief-schema-and-persistence.md`
  — sibling ticket this driver depends on: the TopicBrief schema, its
  UNVERIFIED representation, and its per-topic persistence/replace
  primitives. This ticket calls that interface; it does not redefine it.

## Decisions already locked (do not re-litigate)

- **Pinning semantics:** artifacts and fridge contents are per-topic facts,
  written once; idea re-rolls never re-run research or faction reading; an
  explicit refresh re-runs everything and REPLACES stored state.
  (Generalizes the ratified gap-pin decision.)
- **Checker is two-layer and never self-graded:** code checks (field
  non-empty, citation present and drawn from the actually-gathered URL set)
  plus one cheap cross-family LLM call judging per-field specificity. Max 2
  fail-and-repair rounds; each failed field's gap becomes the next research
  query. On exhaustion: brief persisted with UNVERIFIED stamps, run halts for
  the operator. A passing brief flows onward with no blocking gate.
- **Research stage extends the existing context-gathering loop** (LangGraph
  plan/act loop, Reddit + Tavily + Firecrawl tools, community lookup).
  Existing caps unchanged: 20 tool calls, $1.00 Apify per run, 3-stale-
  Reddit-calls saturation guard, reaction+context floor — this driver reuses
  them, it does not redefine them.
- **Fridge becomes the universal raw-material store:** all gathered web text
  AND Reddit reaction text (upvote tags preserved) indexed per topic. Refresh
  semantics: re-research REPLACES a topic's fridge rows and artifacts
  (delete-then-index). Retrieval interface unchanged (topic-scoped semantic
  search).
- **Ideation reshapes the existing slim pitcher:** input becomes the two
  pinned artifacts (not event + gap); slate grows to 8-15 one-line ideas;
  every camp covered at least once; each idea tagged with target camp + mode.
  Re-rolls: same pinned inputs, prior loglines passed as do-not-repeat.
- **Idea record keeps the existing pick-level contract** so the downstream
  director (StoryArchitect D1), craft gates, and writer are untouched.
- **Human control points:** operator can read/correct both artifacts at any
  time; forced halt only on an UNVERIFIED brief; operator picks at the slate.
- **The old single-consensus gap agent and Path A stay in place**, untouched
  — this driver does not extend, replace, or delete them.
- **Known boundary, explicitly deferred:** research tools ingest live web
  text; a poisoned page riding into the pinned brief (indirect prompt
  injection) is noted, not mitigated, by this ticket.

## Acceptance criteria

1. Given a topic with no pinned state, running the driver executes research,
   then the checker (with up to 2 repair rounds triggered by failing
   fields), then faction read, then ideation, in that order — observable via
   call order/counts on injected fakes.
2. If the checker still has UNVERIFIED-stamped fields after the 2-round
   repair bound, the driver persists that brief with the stamps and HALTS:
   the faction reader and the ideation component are never called, and no
   slate/pick is offered to the operator.
3. If the brief passes — first attempt or after 1-2 repair rounds — the
   driver proceeds automatically through faction read and ideation with no
   blocking approval prompt in between.
4. Given a topic WITH pinned state and no `--refresh`, running the driver
   again calls neither the research component, the checker, nor the faction
   reader — it loads the stored Topic Brief and Faction Map and calls only
   the ideation component.
5. On that pinned re-roll, the ideation component receives the previously-
   shown idea loglines as its do-not-repeat input, and the returned slate
   excludes them.
6. Given a topic WITH pinned state and `--refresh`, running the driver calls
   research, checker, and faction reader again regardless of the existing
   pinned state, and the persistence calls REPLACE (not append to) the
   topic's stored brief, faction map, and fridge rows — a read after the
   refresh returns only the new content.
7. The operator's pick at the printed slate is persisted and a handoff
   artifact is produced in the same record/JSON shape the existing
   `pitch_angles.py` driver already produces for a picked angle.
8. An operator skip/invalid selection at the slate persists the run's
   artifacts/slate (mirroring the existing skip behavior) but writes no
   handoff and approves nothing.
9. Every stage (research, checker, faction reader, ideation) is invoked
   strictly through injected dependencies — the driver runs end-to-end in
   tests with zero network calls and zero real LLM calls when fakes are
   injected for all of them.

## Test notes

- Seams: fake LLM per stage (research planner, checker, faction reader,
  ideator) — the pattern every existing monitor-agent test already uses;
  injected `item_fetcher` fakes for Apify/Tavily/Firecrawl (no network);
  injected DB session for artifact + fridge persistence; the driver itself
  is the top seam — a wire test with every dependency faked, mirroring
  `tests/monitor/test_pitch_angles.py`'s style (assert on fakes' call
  lists/counts, persisted rows, and handoff JSON content).
- PRD-mandated behaviors THIS ticket's tests must cover (the driver-owned
  slice of the PRD's full Testing Decisions list): the checker repair loop
  respects the 2-round bound; the UNVERIFIED + halt path (halts, does not
  reach faction/ideation, persists the stamped brief); a plain re-roll skips
  research/checker/faction entirely; `--refresh` re-runs everything and
  REPLACES rather than stacks stored artifacts/fridge rows; a re-roll
  excludes previously-shown ideas; the pick hands off in the existing
  contract.
- Explicitly OUT of this ticket's test scope, even though the PRD names them
  in Testing Decisions: checker fails a citation-less field (checker
  ticket), faction top-up triggers exactly once and only below floor / THIN
  DATA stamp / camp cap applied post-emergence / single-camp map accepted
  (faction ticket), slate covers every camp (ideation ticket). This ticket
  only proves the orchestration and pinning control flow around those
  stages — fake them, do not re-test their internals here.
- Build-time-only (not this ticket, not CI): the faction prompt's
  shuffle-stability validation on real threads.

## Who types

The pinning/halt/refresh control flow — deciding fresh-vs-pinned-vs-refresh,
enforcing the 2-round repair bound, the UNVERIFIED halt, threading
do-not-repeat into a re-roll — is a genuinely new decision, not a byte-for-
byte mirror of `_PinnedGapAgent` (that precedent pins ONE stage; this spans
four stages with different halt/replace semantics), so per the named-mirror
test it is user-implemented, AI reviews — gate model applies (user
decides-before the branch logic and halt policy; AI may then type to that
spec, user predicts/traces after). The CLI plumbing around it — argparse
setup, `load_dotenv`, the `sys.stdout.reconfigure(encoding="utf-8")` Windows
console fix, the `__main__` wiring of real components — is a named mirror of
`pitch_angles.py`'s own `main()` and is AI-typed-by-default under the
named-mirror carve-out.

## Open questions

- Whether the driver inlines a call into the existing (unchanged)
  StoryArchitect/craft-gate/persist tail after the operator's pick — the way
  `run_pitch_pipeline` does today — or stops at writing the approved record
  + handoff JSON for a separate existing entry point to consume later. The
  PRD's Out of Scope section and this ticket's own "slate-out" framing don't
  resolve which.
- The exact shape of the "is this topic pinned" check and the load/save/
  replace calls the driver makes — depends on ticket 01's still-open table-
  placement decision (extend `TrendingEventRecord` vs. a new topic-scoped
  record) and on the faction/ideation tickets' own persistence choices.
- Whether the fridge's delete-then-write on `--refresh` is a call this
  driver makes directly (delete rows, then call `index_web_text`) or a
  single replace-aware function the fridge module exposes instead — current
  `index_web_text` is append-only per its own docstring.
- Whether `--refresh` and a re-roll can be requested in the same invocation,
  or whether `--refresh` always means a full fresh run with no re-roll
  option in that call — the PRD states the two behaviors but not their
  interaction.
- Whether the operator's pick happens interactively in the same process that
  printed the slate (like `pitch_angles.py`'s `input()`), or whether Exilus
  also needs a non-interactive `--choice`-style override (like
  `repitch_event.py`) for a pick made in a later run — not specified by the
  PRD.
- (RESOLVED by coverage audit 2026-07-17: no new "slate artifact" column exists
  or is needed — every slate idea already persists as its own `AnglePitchRecord`
  row with `idea_json`, exactly as the current driver does. The do-not-repeat
  list for a re-roll is reconstructed by querying the topic's previously
  persisted idea rows' loglines; appending happens naturally as each new
  slate's rows persist. This driver owns that query + threading.)
- Whether raw material gets indexed into the fridge by this driver directly
  (as `pitch_angles.py` calls `index_web_text` inline today) or internally by
  the research component before it returns — affects this ticket's exact
  dependency list.
- **PENDING USER DECISION (User Story 22, coverage audit found no owner):** the
  mechanism by which the operator CORRECTS a stored brief/faction map (reading
  is trivial; correcting is not). Options to put to the user before this
  ticket starts: (a) a small CLI edit flow — dump the artifact to a JSON file,
  operator edits it, a command re-imports and re-pins it; (b) a direct-DB edit
  helper script; (c) treat the handoff JSON file as the editable source of
  truth the driver re-reads. Until decided, US22 is only half-delivered
  (read yes, correct no) — do not silently drop it.
