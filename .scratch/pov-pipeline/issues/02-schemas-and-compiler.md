# 02 — POV schemas + prompt compiler (pure function)

**What to build:** the data contracts and the deterministic compiler. Pydantic models for the lane: a POV pitch (who you are / where / what happens / the turn), a POV script (scene setting, duration 10|15, ordered beats — each 1-2 physical actions, optional dialogue line, diegetic audio events — plus world prose block). The compiler is pure code: script in → final prompt text out. It injects the fixed skeleton clauses VERBATIM from the ticket-01 config block, chains beats as prose (never bracketed timestamps), appends `Audio:` prose lines, scrubs kill-list vocabulary from LLM-authored prose, and enforces the 60-100 word body target. It also emits the render CLI command string (seedance_2_0, 9:16, chosen duration, 480p) and the cost line from measured rates.

TDD at seam 2 (the agreed pure-function seam): tests feed fixture scripts and assert on output text only.

**Blocked by:** 01 — POV grammar block in render rules config.

**Status:** ready-for-agent

- [ ] Models follow house conventions (extra="forbid", multi-line docstrings)
- [ ] Compiler output contains every fixed skeleton clause byte-verbatim from config
- [ ] Kill-list words in input prose never survive to output (test proves scrub, not prompt discipline)
- [ ] No bracketed timestamps in output under any input
- [ ] CLI command + cost line match the chosen duration and measured rate table
- [ ] Tests green at seam 2; ruff/mypy clean on new modules
