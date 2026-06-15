# Bug Log

Track every shipped feature that fails, what was tried, and what fixed it.

## Status Legend
- `open`: issue is reproducible and unresolved
- `monitoring`: fix shipped, observing behavior
- `closed`: fix verified

## Entries

### BUG-001 - traced() drops the `kind` arg → LLM calls log as spans, not generations
- Date opened: 2026-06-14
- Status: open
- Feature: Langfuse observability (`src/observability/tracing.py`), affects EVERY `@traced` LLM call (extractor, writer, judge)
- Environment: Langfuse US cloud (live — `get_client().auth_check()` returns True with config/.env keys)
- Error/behavior: `traced(name=..., kind="generation")` accepts `kind` but never forwards it.
  Line 31 calls `observe(name=..., capture_input=..., capture_output=...)` with no `kind`. So
  calls decorated `@traced(kind="generation")` (e.g. `anthropic_llm.parse`) likely record as
  plain SPANS, not GENERATIONS. Token/cost/`cache_read_input_tokens` are generation-specific
  fields → suspected missing on these spans. This is the suspected reason the Opus 4.8 cache
  question (cache_read vs 4096-token min) has never had a clean dashboard answer.
- Reproduction steps:
1. Run any traced LLM call (e.g. `run_rubric_eval --fixtures data/golden/writer_floor_static.jsonl`).
2. Open the Langfuse dashboard, find the `anthropic_llm.parse` observation.
3. Check whether it is typed GENERATION and whether token/cache fields are populated.
- Attempted fixes:
1. (none yet — logged, deferred per scope; surfaced during the judge-floor-probe feature 2026-06-14)
- Root cause: SUSPECTED — `kind` plumbed into `traced()` but not passed to `langfuse.observe`.
  Needs (a) dashboard confirm the fields are actually absent, AND (b) check the langfuse SDK
  `observe()` signature actually takes a `kind`/`as_type` param before patching.
- Final fix: TBD
- Date fixed:
- Validation evidence: TBD

