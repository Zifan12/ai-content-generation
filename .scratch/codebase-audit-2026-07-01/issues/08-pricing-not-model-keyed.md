# pricing.py applies flat Sonnet rates regardless of the response's actual model

Status: ready-for-agent
Severity: High (AUD-H7)

`src/blueprints/pricing.py:15-17`: one flat `PRICE_PER_M_TOKENS` table; `compute_response_cost` never reads `resp.model`. Correct today only because `BlueprintExtractor` hardcodes Sonnet — but `AnthropicLLM`'s own constructor default is Haiku (`anthropic_llm.py:25`), so a single `BlueprintExtractor(llm=AnthropicLLM())` call silently mis-prices every row it writes. This figure feeds `today_extraction_spend()` → the daily budget guard (`recurring.py`), so under-pricing a more expensive model is a guard bypass, not just a reporting error.

Fix direction: key the rate table by `resp.model` (exact model-id strings), raise `KeyError`/fail loud on unknown models rather than defaulting. Regression test: two `ExtractorResponse` rows with different `model` values → different costs; unknown model → raises.

Folds naturally into ADR-0007's single rates module if approved.

## Comments
