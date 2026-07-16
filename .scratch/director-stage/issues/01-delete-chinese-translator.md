# 01 — Delete the Chinese translator stage

**What to build:** The composed English scene prompt goes straight to the Higgsfield CLI. The
English→Chinese translation stage no longer exists — not disabled behind a flag, deleted. A smoke run
produces a package and a payload with one fewer LLM call and no translation status, and the prompt sent
to Seedance is the English the director wrote.

**Why:** The "write in Chinese, never English" rule traces to a practitioner doc for the **OpenArt**
frontend — not Higgsfield — with no justification anywhere in its 598 lines, and the repo's own
`ai_video_resources/INDEX.md` flags that file "cherry-pick claims, never adopt wholesale." The only
source matched to both Higgsfield **and** Seedance reports English phrasings transfer near-directly.
The genuine Chinese-fidelity claims in the corpus are for Kling and Jimeng — different models. The
project's own translation spec admits the premise was never tested: *"trust that Chinese wins, no
pre-A/B."*

This is deleting an unvalidated premise, **not** fixing a bug. The stage has a designed 5-check graceful
fallback and is not silently crashing. A real substring bug exists in its dialogue validation; it becomes
moot.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The translation module and its tests are gone; no dead imports or config keys remain.
- [ ] The render-rules entries documenting the translation step are removed, not left as stale comments.
- [ ] The adapter composes and sends the English prompt; no translation hook remains in the path.
- [ ] A dry-run smoke on an existing pitch completes and its payload prompt is English.
- [ ] The LLM seat for translation is removed from provider config if it serves nothing else.
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run mypy src/` all pass.
