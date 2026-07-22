# PRD: POV Pipeline — slice ③ (first-try success package)

Status: ready-for-agent
Date: 2026-07-22
Evidence base: two live POV posts (2026-07-18, 2026-07-22); POV-era render failure record (BUG-030→037, Higgsfield transaction history, render sheets); Second Brain consult 2026-07-22 (Deming/SoPK primary, Commey secondary — recurrence gate, prediction field, objective-vs-taste tagging all sourced there); grilling session 2026-07-22 resolved every fork below, decisions user-ratified.

## Problem Statement

Every failed paid render burns credits. The operator's stated goal is getting the wanted video on the first try — and when that's impossible (the generator is stochastic), failing cheaply and never paying for the same lesson twice. Today, known failure classes are only partially blocked before spend: script structure and banned vocabulary are enforced in code, but other paid-for lessons (effect-detachment, camera drift, ref-set mistakes) live in markdown docs and session memory, so nothing mechanical stops them from reaching a paid render again. Watch verdicts are recorded ad hoc in prose, so defects aren't countable, one-off stochastic noise is indistinguishable from recurring defects, and the mandatory 480p-probe-before-final ladder is a convention on the render sheet that nothing enforces. There is no per-story spending brake in tooling — the 2-retake stop and the proposed credit cap exist only as spec prose.

## Solution

Three additions to the POV lane, all deterministic code and plain files — no LLM judges, no databases, no automated rendering:

1. **Failure audit → pre-spend code checks.** A one-time audit of every POV-era paid render failure produces a defect-class taxonomy. Every class that code can catch becomes a deterministic pre-spend check (blocking, with the lane's existing bounded-repair convention where applicable); every class code cannot honestly catch is added to the operator's watch checklist, explicitly labeled a taste call — never faked as a code check.
2. **Verdict log.** After each watched render the operator logs a verdict through a new CLI flow: pass/fail, defect class from the fixed taxonomy (plus an `other` escape with free-text note), and an objective-vs-taste tag. The pipeline auto-writes a prediction block at sheet-generation time (which rules were active, what should therefore appear on screen) so every verdict tests the ruleset's theory, not just tallies outcomes. A recurrence gate governs rule changes: the first sighting of a defect class is a data point only; a rule row is drafted for ratification only when the same class recurs on ≥2 independent renders. Rules are always human-ratified, never auto-written. The log is seeded retroactively from documented watched verdicts only, tagged as retrospective.
3. **Probe gate + spending brakes.** The render sheet initially emits only the 480p probe command. The final-resolution command is released by logging a probe PASS. A prompt whose exact compiled hash already has a probe PASS on record is auto-exempt; a deliberate skip is available via an explicit force flag that is itself logged. Two failed retakes park the story with structured forensics; a hard 150-credit per-story cap is enforced by the same flow — once crossed, no further render commands are released for that story.

Build order: this slice ships before the next video (post #3), which becomes its first live run.

## User Stories

1. As the operator, I want every failure class we have already paid for turned into a pre-spend code check, so that no known defect ever reaches a paid render again on any topic.
2. As the operator, I want checks derived from the POV-era failure record (2026-07-17 onward), so that the rules encode the current register's physics rather than re-litigating deprecated lanes.
3. As the operator, I want failure classes that code cannot catch listed on the watch checklist and labeled as judgment calls, so that the pipeline never pretends a taste call is mechanically verified.
4. As the operator, I want a single CLI step to log my watch verdict, so that recording a pass/fail takes seconds and never gets skipped.
5. As the operator, I want to pick the defect from a fixed numbered taxonomy, so that the same failure mode always counts under the same name across sessions.
6. As the operator, I want an `other` option with a free-text note, so that a brand-new failure mode never blocks logging and still carries enough detail for later classification.
7. As the operator, I want an `other` entry promoted into the taxonomy when it recurs, so that the taxonomy grows from evidence, not speculation.
8. As the operator, I want each fail tagged objective (operationally defined) or taste (subjective judgment), so that future audits can separate measurable defects from preference calls.
9. As the operator, I want the pipeline to auto-write a prediction block on every render sheet naming the active rules and their expected on-screen outcome, so that each verdict confirms or refutes the ruleset's theory with zero extra typing from me.
10. As the operator, I want a fail on a predicted-safe render to read as "rule was active and still failed," so that insufficient rules are distinguishable from gaps no rule covers.
11. As the operator, I want the first occurrence of a defect class logged as a data point without any rule change, so that one-off stochastic noise never over-constrains future prompts.
12. As the operator, I want a rule row drafted only when a defect class recurs on at least two independent renders, so that every ratified rule targets a real recurring cause.
13. As the operator, I want to personally ratify every rule row before it lands in the render config, so that a wrong rule can never silently forbid good output forever.
14. As the operator, I want the verdict log seeded from documented watched verdicts only, each tagged retrospective, so that lessons already paid for count toward recurrence without inventing labels for unwatched renders.
15. As the operator, I want the render sheet to emit only the 480p probe command at first, so that I cannot accidentally discover a defect at final-resolution prices.
16. As the operator, I want logging a probe PASS to release the final-resolution command for that exact prompt, so that the gate lives in the same flow as the verdict and costs me no extra steps.
17. As the operator, I want a prompt whose exact compiled hash already has a probe PASS to skip re-probing automatically, so that re-renders of proven configs don't waste probe credits.
18. As the operator, I want an explicit force flag to skip the probe when I judge it unnecessary, so that the gate never has to be worked around outside the tooling.
19. As the operator, I want every probe skip recorded in the log, so that a failed skipped-probe render is attributable to the bypass, not the gate.
20. As the operator, I want the story parked automatically after two failed retakes, so that a stubborn story cannot silently eat the credit budget.
21. As the operator, I want a parked story to carry structured forensics (verdicts, defect classes, predictions, spend), so that a future session can resume the post-mortem without re-deriving anything.
22. As the operator, I want a hard 150-credit per-story cap enforced by the tooling, so that total spend per story is bounded in money, not just attempts.
23. As the operator, I want the cap and retake counters tracked from the run's own logged verdicts, so that the brakes work from real recorded spend rather than my memory.
24. As the operator, I want every new artifact (verdict records, lane-wide log, forensics) stored as plain files per run, so that any run can be post-mortemed without a database.
25. As the operator, I want the lane-wide log to be a single append-only file, so that recurrence counting and future analysis read one place.
26. As the operator, I want every new check and rule row to carry an evidence tag, so that future sessions can trace any constraint back to the render that paid for it.
27. As the operator, I want the next video produced through this tooling end-to-end, so that the slice is validated by a real post rather than fixtures alone.

## Implementation Decisions

- **Failure audit is a build-time deliverable, not runtime code.** Sources: the POV-era bug records (BUG-030→037), render sheets and job artifacts, Higgsfield transaction history, and the render-decision docs. Output: the seed defect-class taxonomy (each class marked code-catchable or watch-only, with evidence tags) and the list of new pre-spend checks. Third-person-era lessons enter only where already distilled into standing docs.
- **New pre-spend checks extend the existing deterministic enforcement layer** (same pattern as the current structural checks and compiler scrub): pure functions, script-or-prompt in → named violations out, wired into the existing bounded-repair path where the defect is repairable and into hard pre-compile failure where it is not. No LLM call anywhere in the check path.
- **Verdict flow is a new subcommand on the existing lane driver.** Inputs: run directory, pass/fail, defect class (fixed taxonomy + `other`), optional note, objective-vs-taste tag, resolution rendered. Effects: writes a verdict record into the run directory, appends to the lane-wide log, updates recurrence counters, and — on probe PASS — emits the final-resolution command (into the sheet and to stdout).
- **Prediction block is compiler-derived.** At sheet-generation time the compiler records which rules/checks fired on this prompt and a mechanical statement of expected on-screen behavior per rule. Stored in the run directory and printed on the sheet above the watch checklist.
- **Recurrence gate: ≥2 independent occurrences** (different renders; different topics when available) of the same defect class before a rule row is drafted. Drafted rows follow the existing envelope write-back convention: AI drafts with evidence tags, operator ratifies before the config changes. Qualitative heuristic, not statistical control limits (Deming consult's own caveat).
- **Probe gate state lives in the run directory** (plain files), keyed by the compiled prompt's hash. Auto-exemption consults the lane-wide log for a prior PASS on the identical hash. The force flag is recorded as a distinct event type.
- **Spending brakes:** per-story credit tally computed from logged verdicts' resolution/duration at the measured rate table; the verdict subcommand refuses to release further commands once 150 credits are crossed or a second retake has failed, and instead writes the parked-story forensics file. Both thresholds are config values, not literals.
- **Retro-seeding:** one-time script or documented manual procedure creates `retro`-tagged verdict records for the documented watched verdicts only (the two posted keepers' passes, the documented watched fails). Unwatched or refunded jobs are never seeded — no verdict without an operator watch.
- **Product constants unchanged:** manual rendering (operator pastes commands), 9:16, native audio, no on-screen text; existing publish bookkeeping scripts used as-is.

## Testing Decisions

- Good tests assert external behavior at the lane's two existing seams; no implementation-detail assertions, no new seam classes.
- **Seam 1 — driver level** (prior art: existing driver tests with fake LLM seats and temp dirs). Asserts, against temp run directories: FAIL verdict counts the defect and keeps the final command withheld; PASS verdict releases the final command; recurrence gate drafts nothing at one occurrence and drafts a rule row at two; identical-hash prior PASS auto-exempts the probe; force flag releases the final and records the bypass; crossing 150 credits or a second failed retake refuses further commands and writes forensics; `other` verdicts log cleanly with notes; retro-tagged seeds count toward recurrence.
- **Seam 2 — pure functions** (prior art: existing structural-check and compiler tests). Asserts: each new pre-spend check flags its defect class on crafted-bad input and stays silent on known-good input; prediction block derivation is deterministic for a given prompt + rules; prompt hashing is stable across runs; kill-list and structural behavior unchanged (regression).
- Paid renders, watch verdict quality, and the CLI's real billing behavior are deliberately untested in CI — manual gates by design.

## Out of Scope

- Automated rendering / executor driving the Higgsfield CLI (operator still pastes commands).
- Any LLM judge (trigger unchanged: a failure proving code checks can't see something).
- Database tables or migrations for verdicts (plain files only).
- Multi-generation / >15s stories; Seedance 2.5 anything.
- Posting automation; changes to the publish bookkeeping scripts.
- Audience-performance labels (day-7 views) — separate stream from render-quality labels, untouched here.
- The three banked ops items (1080p+video-ref confirmation render, explosion-bind fix live test, post #3 itself) — they run through this tooling after it ships, they are not build tasks inside it.

## Further Notes

- Deming consult (2026-07-22): design confirmed directionally sound; the recurrence gate, prediction field, and objective-vs-taste tag are its three prescribed corrections, all adopted. Probe gate confirmed as the correct minimal-inspection point — no third inspection tier unless probe/final proves insufficient. Consult flagged as genuinely open: the prompt-generator itself is being iterated topic-to-topic, so common-vs-special-cause separation is strong-but-not-airtight.
- The explosion-bind defect class already has one documented occurrence and a drafted (untested) prompt fix; under the recurrence gate it sits at count 1 — the fix may still be applied per-story as an experiment, but no standing rule lands until recurrence.
- Post #3 is the live shakedown: its render sheet, prediction block, probe verdict, and final release should all flow through the new tooling; any friction found there is slice-③ feedback, not operator error.
