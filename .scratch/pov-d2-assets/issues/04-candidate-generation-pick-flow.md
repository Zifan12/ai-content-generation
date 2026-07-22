# 04 — Candidate generation + pick flow

**What to build:** A declared object with no promoted references triggers still generation instead of a drop-images-yourself sheet: the pipeline states total cost, generates one isolated candidate still per object via GPT Image 2 (deterministic template from the render-rules config: the object's script description + shared style clause + scene vantage; never the composed target frame), writes candidates under the object's `candidates/` area, records the spend, and halts with a pick sheet. The operator promotes keepers by file move, then runs the new `assets` release subcommand against the same run — it validates promoted refs and writes the probe command (real absolute ref paths) into the run. No LLM re-spend after promotion. Objects whose refs already exist skip generation entirely (cache hit).

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] Missing object refs → cost line printed BEFORE any image spend
- [ ] One candidate per object per batch, template-built prompt, shared style clause verbatim across the batch
- [ ] Template forbids composed-target-frame content (no basket/hands/staging)
- [ ] Candidates land in `candidates/`; run halts with pick sheet naming paths + promotion gesture
- [ ] `assets <run_dir>` subcommand: validates promoted refs, writes probe command with absolute ref paths into the existing run — no seat re-runs
- [ ] Pre-existing refs skip generation (no spend, no halt)
- [ ] Still spend recorded as plain-file records readable by the verdict tally
- [ ] Higgsfield call isolated behind one fakeable function (existing fake pattern)
