# 06 — First live run (human gate, credits)

**What to build:** nothing — this is the pipeline's proof run. Operator (with agent assistance) runs one real `--idea` story end-to-end: live script seat, compiled sheet, MANDATORY 480p sanity render (~30cr @10s), then 720p if sanity passes (~45cr), watch verdict against the sheet's checklist. Results recorded: verdicts into the run's sheet, any defect into bugs.md, any new measured fact into DECISIONS_LOCKED / render rules evidence notes. State credit cost before each render (L7). This ticket satisfies PRD done-criterion #2.

**Blocked by:** 03 — Idea mode end-to-end; 04 — Script craft enforcement.

**Status:** ready-for-human

- [ ] One story rendered through 480p → 720p ladder, costs stated before each spend and billing-verified after
- [ ] Watch verdict recorded on the run's render sheet (pass/fail per checklist item)
- [ ] Any defect logged in bugs.md with evidence; any new measured fact recorded in the locked-decisions file
- [ ] If the story is a QUIET (non-action) narrative, note the outcome explicitly — corpus has no worked example of that register (PRD Further Notes)
