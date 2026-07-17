# 03 — Idea mode end-to-end (the tracer bullet)

**What to build:** `uv run python scripts/pov.py --idea "<full story concept>"` produces a complete run directory: the operator's text wrapped verbatim as the picked pitch (no pitcher call, code-copy doctrine), a POV script authored by the script LLM seat, the compiled prompt, a prompt .txt file, and a render sheet markdown containing the prompt, the copy-paste CLI command, the cost statement, the MANDATORY 480p→720p→1080p ladder wording, the POV watch checklist (angle switch / body leak / beat teleport / text leak), and the location-still escalation lever instructions. Script seat resolves through the existing per-seat provider factory with a per-caller max_tokens override and @traced observability, system prompt as a module-level constant carrying the story-shape rules from the PRD (beat budgets, Setup→Turn→Button with collapsible button, emotion as physical tells, world-prose craft, dialogue placement).

TDD at seam 1 (the agreed driver seam): fake LLM seats, no network, no renders. Mimic the StoryArchitect + its tests as the house pattern exemplar.

**Blocked by:** 02 — POV schemas + prompt compiler.

**Status:** closed

- [x] Idea mode runs end-to-end with a fake seat in tests: run directory created with pitch, script, prompt, sheet artifacts
- [x] Fake records ZERO pitcher calls in idea mode
- [x] Pitch fields byte-identical between operator input and sheet (code-copy proof)
- [x] Render sheet contains: verbatim prompt, CLI command, cost line, mandatory-ladder wording, watch checklist, escalation lever
- [x] Live smoke path documented in the driver docstring (not run in CI)
- [x] Tests green at seam 1; ruff/mypy clean
