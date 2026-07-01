# generation_eval.py is import-broken rot from the retired chain schema

Status: needs-triage
Severity: High (AUD-H8)

`src/evals/generation_eval.py:19` imports `build_naked_envelope` — no longer defined in `content_writer.py`. `_render()` (lines 42-49) reads `package.device`/`package.shots` — fields the single-shot `ContentPackage` no longer has. `ContentWriter.write` called with the retired positional signature (line 96). Any import raises `ImportError` immediately; `scripts/run_generation_eval.py` is dead. Blast radius contained — `harness.py` does NOT import it (verified).

Related dormancy: `src/evals/judges.py` + `generation_eval.py` have zero tests; `tests/evals/test_writer_judge.py` is module-skipped ("parked behind single-shot pivot") — that evals slice executes zero times in CI.

Decision needed (hence needs-triage):
- **Option A:** rewrite the RAG-win-rate gate against the single-shot schema — and fix the position bias (AUD-H11) in the same pass; the `seed` param is already reserved for the slot swap.
- **Option B:** delete `generation_eval.py` + `run_generation_eval.py` until the multi-shot writer (06-27 spec) lands, then rebuild against the v2 schema.

Audit lean: Option B — the writer schema is about to change again (multi-shot), so a rewrite now targets a schema with a short shelf life. Don't leave it importable-looking either way.

## Comments
