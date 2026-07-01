# pitch_angles: `--topic --no-llm` silently ignores `--no-llm`, runs full paid pipeline

Status: closed (fixed 2026-07-01)
Severity: High (AUD-H2)

`scripts/pitch_angles.py`: `args.no_llm` is consulted exactly once, inside the `if args.topic is None:` branch (line 485). With `--topic` set, the flag is silently dropped — LLM clients, the BGE-M3 embedder, and `ContextAgent.gather()` (Apify + multiple Anthropic calls) all run, despite `--no-llm`'s documented "print raw scraped events and exit" promise.

Fix direction: `parser.error("--no-llm and --topic are mutually exclusive")` when both are set (simplest honest behavior), OR honor it in Path B: run `context_agent.gather()`... no — that spends too. Cleanest is the argparse mutual exclusion; a free Path B preview doesn't exist by construction.

Regression test: invoke `main()` with both flags monkeypatching `AnthropicLLM`/`BgeM3Embedder`/`ContextAgent` to raise if constructed — same pattern the audit recommends for the already-shipped `--no-llm` ordering regression (commit 1e129eb, AUD-H13e).

## Comments

**2026-07-01 — FIXED** via argparse mutual exclusion: `parser.error(...)` fires immediately after `parse_args()` when both `--topic` and `--no-llm` are set (exit code 2, usage printed, nothing constructed, nothing spent). Validated: 111/111 tests pass. The suggested regression test is NOT yet written — it belongs to issue 14's test-debt batch (learning-scope, user writes).