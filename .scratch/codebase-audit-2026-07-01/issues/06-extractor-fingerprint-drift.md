# Extractor cache fingerprint assembled from three independent literals

Status: ready-for-agent
Severity: High (AUD-H5)

`src/blueprints/extractor.py`: the real call passes `max_tokens=2048` (line 232), `sampling_params = {"max_tokens": 2048}` is a separate literal (line 235), and `reparse_from_cache` hardcodes a third copy (line 293). `temperature` is absent from the fingerprint even though `parse_with_raw` accepts it.

Failure: edit `max_tokens` at one site (the exact edit this project has made before — shared-max-tokens truncation incident) → `extract()` and `reparse_from_cache()` compute different fingerprints → stale cache hits or permanent cache misses, silently. Undermines ADR-0004's invalidation model.

Fix direction: one module-level `SAMPLING_PARAMS` dict consumed by the API call, the fingerprint in `extract()`, and the fingerprint in `reparse_from_cache()`; include temperature if ever set. Regression test: extract-then-reparse round-trip returns the cached row (no second LLM call) after changing nothing; changing the constant makes reparse miss.

Adjacent low (same file, fold in): `build_envelope` hardcodes `extractor_model='claude-sonnet-5'` regardless of `llm.model` (AUD-L3); `except IntegrityError` should use a `begin_nested()` savepoint + log instead of full-session rollback (AUD-M15).

## Comments
