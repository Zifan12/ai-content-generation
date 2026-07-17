# 05 — Topic mode: pitch slate + interactive pick

**What to build:** `uv run python scripts/pov.py --topic "<seed>"` generates a 3-5 pitch slate from the pitcher LLM seat (desire-first, each pitch: who you are / where / what happens / the turn — judgeable in seconds), prints it, takes an interactive pick by number, then flows into the SAME downstream as idea mode (script seat → compiler → render sheet). `--topic` and `--idea` are mutually exclusive; passing both fails loud. Pitcher seat follows the same house conventions as ticket 03's script seat (per-seat factory, max_tokens override, @traced, module-level system prompt).

**Blocked by:** 03 — Idea mode end-to-end.

**Status:** ready-for-agent

- [ ] Topic mode with a fake pitcher seat: slate of 3-5 pitches produced, pick honored, downstream artifacts identical in shape to idea mode
- [ ] Picked pitch fields code-copied downstream (never LLM-echoed)
- [ ] --topic and --idea together = loud argument error
- [ ] Slate persisted in the run directory (unpicked pitches kept for post-mortem)
- [ ] Tests green at seam 1; ruff/mypy clean
