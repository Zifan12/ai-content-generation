# 08: Build-time faction-map shuffle-stability validation

Status: ready-for-human

## Scope

This ticket builds the one-time, build-time (paid, manual, **not CI**) validation
harness that answers the question the whole Exilus redesign exists to answer: does the
faction-map reader actually fix the instability that killed the old single-consensus gap
read, or does it just repaint the same non-determinism under a new schema?

The harness takes 2-3 real Reddit threads (comments already filtered by the existing
≥5-upvote floor — the same filter production will use), produces shuffled and/or
subsampled variants of each thread's comment set, runs the faction-map reader
independently on every variant, and assembles a report the user reads to judge whether
the same camps re-emerge across variants of the same thread. The harness does not
self-certify a verdict — per repo convention, stability/quality verdicts are judged by
the user, not the system under test.

This is validation-only. It assumes the faction-map reader (prompt + parsing stage) is
already implemented by the faction-read ticket; this harness runs against that stage
once it exists, it does not build the reader itself. It is explicitly NOT a runtime
double-roll (the PRD rules that out — build-time only) and NOT the n≥4 ablation
methodology itself (that governs any *subsequent prompt tuning* if this validation
finds instability — a follow-up, not this ticket's deliverable).

Caution carried into this ticket: `scripts/run_pitch_ablation.py`, the repo's existing
paired-arm ablation script, imports `GapAnalysis` from `src/monitor/schemas` and calls
`StoryPitcher.pitch(event, gap)` — the exact event+gap contract this PRD's ideation
stage reshapes into a brief+map contract. That script (and its sibling ablation
scripts) will not run as-is once the ideation stage is reshaped; anything reused from
its structure (fixture loading, per-event try/except isolation, EvalRun persistence
shape) must be adapted to the new artifact contracts, not assumed to import cleanly.

## Existing code to read first

- `scripts/run_pitch_ablation.py` — the repo's reference implementation of the
  paired-fixture validation pattern this harness should structurally resemble (CLI
  shape, per-item try/except isolation so one bad thread doesn't kill the run, stating
  cost/LIVE SPEND up front, git-SHA-tagged output). Also the concrete example of "will
  not run against the new contracts": it imports `GapAnalysis` and calls
  `StoryPitcher.pitch(event, gap)`, both slated for replacement in this PRD.
- `src/monitor/gap_agent.py` — the CURRENT single-consensus reader (one
  `dominant_emotion` + one `audience_want` per event) whose cross-run instability is
  the proven root cause this validation exists to catch (Problem Statement: "the same
  Reddit thread was re-read into six different 'consensus' summaries across runs").
  Read it for the prompt-construction pattern (module-level system-prompt constant,
  per-caller `max_tokens` override, untrusted-data wrapped in tags) the not-yet-built
  faction-reader will follow, and as the negative example the shuffle-stability probe
  must show is actually fixed, not repainted, in the new reader.

## Decisions already locked (do not re-litigate)

- "I want the faction-map prompt validated once at build time by a shuffle-stability
  test (same camps from shuffled/subsampled comments), so that I know the instability
  that killed the old gap reads is actually fixed, not repainted." (User Story 24)
- "Build-time (paid, manual, not CI): shuffle-stability validation of the faction
  prompt on 2-3 real threads — same camps must re-emerge from shuffled/subsampled
  comments before the prompt is trusted; repo's existing ablation methodology (n≥4,
  user judges blind) applies to any subsequent prompt tuning." (Testing Decisions)
- Out of scope: "Runtime stability double-rolls of the faction read (build-time
  validation only)." — no runtime re-roll or voting mechanism; this is a one-time
  pre-trust check, not a production safeguard.
- Camp emergence is unconstrained during generation; a cap of 5 is applied only
  afterward as a filter, and a single camp is legal when the audience is unanimous
  (Implementation Decisions — Faction Map bullet; User Stories 12-13). The validation
  harness must not itself impose or normalize a camp count — it reports whatever
  emerged per variant.
- Faction Map built only from comments that already survived the existing ≥5-upvote
  floor (User Story 16) — the real threads fed into this harness must be filtered the
  same way production input will be, not raw unfiltered threads.
- Camp record shape the report is comparing across variants: name, feeling,
  surface_want (audience's own words), deeper_desire (marked INFERRED), evidence
  quotes with upvote counts, weight (share of surviving comments) (Implementation
  Decisions — Faction Map bullet).
- Prompt-text ratification ("system prompts are AI-drafted and user-ratified per repo
  convention, at implementation time, not in this spec" — Out of Scope) means this
  harness runs against whatever faction-reader prompt that other ticket produced; it
  does not draft or tune that prompt itself.

## Acceptance criteria

1. A standalone script exists that, given a real Reddit thread's comment set already
   filtered by the ≥5-upvote floor, produces multiple shuffled and/or subsampled
   variants of that same comment set (each variant contains only comments drawn from
   the source set — no comment introduced that wasn't in the original floor-passing
   set).
2. The script runs the faction-map reader independently against every variant of each
   of 2-3 real threads, and collects the resulting camp list per variant.
3. The script's output is a human-readable report listing, per thread, the camps
   produced by each variant — with no automated pass/fail verdict computed. Whether
   "the same camps re-emerged" is left to the user reading the report.
4. The variant-generation step (shuffle/subsample given a fixed comment list) does not
   itself call any LLM or network resource, and is exercisable in a unit test using a
   fixed fake comment list with no live dependencies.
5. Before performing any paid faction-reader call, the script reports the number of
   LLM calls the run will make (threads × variants), consistent with repo convention
   of stating cost before spend.
6. Nothing in the test suite or any CI configuration invokes this script automatically
   — it is only ever run manually by the operator, mirroring how
   `run_pitch_ablation.py`'s own LIVE SPEND path is never exercised by `pytest`/CI.

## Test notes

- Seams: fake/injected faction-reader response for unit-testing the harness's own
  control flow (variant generation, per-variant bookkeeping, report assembly) — the
  live paid faction-reader call itself is manual and out of the automated test suite,
  same seam pattern as every other monitor-agent test (fake LLM) but exercised here
  only against the harness's plumbing, not the reader's prompt quality.
- PRD-mandated behaviors this ticket's tests must cover:
  - variant generation never drops the ≥5-upvote floor requirement — no sub-floor
    comment can appear in a variant, because the input set is already floor-filtered
    and variants are strict shuffles/subsets of it.
  - the harness's report/aggregation step does not cap or force camp count — feed it
    a fake response with 1 camp and a separate fake response with 5+ camps and confirm
    both pass through into the report unmodified (covers single-camp-legal + no
    harness-side cap, User Stories 12-13).
  - the harness treats each of the 2-3 threads independently — variants and camps from
    one thread never leak into another thread's report section.
- Not test-assertable in the traditional sense (it is a paid, manual, human-judged
  probe, not a pipeline stage with a contract): whether the faction-reader's camps
  are actually "the same" across variants. That judgment belongs to the user reading
  the report, per this PRD's Testing Decisions and the repo-wide convention that
  taste/quality verdicts are the user's, not a self-graded check.

## Who types

Pure-ops sub-parts (AI-typed-by-default): any boilerplate reused from
`run_pitch_ablation.py` — the `git_sha()` helper, `dotenv` loading, argparse
scaffolding — adapted, not assumed to import cleanly against the new contracts.
Everything decision-bearing (what counts as a "variant," how many, subsample ratio,
what the report shows and how it's laid out for judging, which 2-3 threads to use) is
user-implemented per the repo teaching model; the gate model applies — user decides
the variant/report design before typing, AI reviews after.

## Open questions

- Exact number of variants per thread and the subsample ratio/strategy (e.g. drop N%
  of comments vs. hold out a fixed count) — PRD says "shuffled/subsampled," not a
  count or ratio.
- Whether results should persist to `eval_runs` (as `run_pitch_ablation.py` and
  `run_self_agreement.py` do) or are console/file output only — PRD doesn't say this
  one-time validation needs a durable metrics row.
- Whether the report does any automated grouping/similarity aid (e.g. clustering camp
  names across variants to ease comparison) or is a raw side-by-side dump — PRD only
  requires the user be able to judge; it doesn't specify report mechanics.
- Which specific 2-3 real threads to use — left to implementation time.
- If this first validation pass finds instability: is building the n≥4 blind-judged
  ablation harness for subsequent prompt tuning part of this ticket or a separate
  follow-up ticket? PRD says the methodology "applies to any subsequent prompt
  tuning" but doesn't scope who builds that harness or when.
