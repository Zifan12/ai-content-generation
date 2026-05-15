# Extractor cache invalidation policy

The `extractor_responses` table caches raw LLM responses keyed by `compute_prompt_fingerprint(SYSTEM_PROMPT, envelope, model, sampling_params)`. Any change to one of those four inputs invalidates the cache for affected rows. This ADR records the engineering rules that govern when a Blueprint-schema change preserves the cache vs. invalidates it, so future schema evolution can be planned (and budgeted) deliberately.

## Cache-safe changes (free reparse, no LLM cost)

- **Add a value to an existing `Literal[...]` enum.** Old cached responses contain only old values; all still validate under the extended Literal.
- **Add a nullable field** (`new_field: Foo | None = None`). Old dicts lack the key; Pydantic defaults to `None` and reparse passes.
- **Remove a field.** Pydantic ignores extra keys in stored dicts.
- **Rename a field with `Field(alias=...)`.** Alias maps the old dict key to the new attribute name.

## Cache-breaking changes (require re-extraction)

- **Add a required field** (no default). Old dicts missing the key raise `ValidationError`. Full re-extraction of all rows.
- **Remove or rename a `Literal[...]` value** without alias. Only the rows whose stored response contains the removed value re-extract; the rest reparse cleanly. Cost is per-affected-item, usually trivial.
- **Change a field's type.** Numeric ↔ string, scalar ↔ list, etc. Full re-extraction.
- **Change `SYSTEM_PROMPT` or `envelope` structure.** Fingerprint changes for every row; full re-extraction.
- **Change `model` or `sampling_params`.** Fingerprint changes; full re-extraction.

## Engineering rules

1. **New fields ship nullable.** Migrate to required only after a re-extraction pass has populated the field for every row.
2. **Prefer adding Literal values over renaming or removing.** Additions are free; removals are per-row.
3. **Use `Field(alias=...)` on every rename.** Cheap insurance; preserves cache for the cost of one extra line.
4. **Treat `SYSTEM_PROMPT` changes as version bumps.** Bump `EXTRACTOR_VERSION` and plan a re-extraction; do not change the prompt mid-version.
5. **Run a coverage check before any Literal lock or value removal.** Counter analysis on the existing corpus reveals how many rows hold values not in the proposed set; that is the re-extraction cost.

## Consequences

The cache earns its keep on additive schema evolution (v3.1 → v3.2 nullable adds, value extensions) and on dev-loop iteration where the prompt is stable. It does not save money on the v3.1 enum lock itself (per ADR-0003: 50 rows re-extract anyway because the lock removes singletons). The first big spend after Phase 4 caching is enabled is the v3.1 re-extraction (~$4–5 with Anthropic prompt caching, ~$6–7 without).

## Considered alternatives

**Re-fingerprint on schema change instead of prompt change** — rejected because the schema is not an input to the LLM call; only the prompt + envelope + model + sampling are. Including schema-version in the fingerprint would invalidate the cache on every Pydantic edit even for purely additive changes, defeating the cache's purpose.

**Cache the parsed Pydantic object instead of the raw dict** — rejected because the parsed object is bound to one schema version. A future v4 schema cannot re-validate against a stored v3.1 object; it can re-validate against the stored raw dict. Storing the dict preserves reparse flexibility.
