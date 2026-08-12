# Drop LLM-emitted float self-ratings from the Blueprint schema

The v1 Blueprint schema carried 7 floats in `[0.0, 1.0]` emitted by the extractor LLM as self-ratings (`hook_strength`, `curiosity_gap`, `immediate_clarity`, `emotional_charge`, `payoff_quality`, `replayability`, `comment_trigger`, `shareability`) plus a `confidence` self-rating. All are dropped in v3 because: (1) they fail the round-trip rule — the generator cannot aim at "0.83 curiosity_gap"; (2) Cohen's kappa does not apply to continuous values, so the eval gate cannot score them; (3) `MECHANIC_FIELDS` in `src/evals/blueprint_eval.py` was the only declared consumer and is never read by any code path.

## Consequences

Continuous virality signal — if the ML predictor in P4 needs it — must come from **real outcome metrics** (`view_count`, `outcome_view_percentile` written by the Publish Loop in P3.5) rather than LLM self-rating. The v1 corpus of 120 BlueprintRecords retains the float fields for audit; v3 re-extraction drops them. Reversing this decision would require a v4 schema bump and ~$4.50 of Sonnet re-extraction.

## Considered alternatives

Keep the floats as ML predictor features. Rejected because LLM self-rated floats are notoriously noisy with no kappa to bound their reliability, and one-hot-encoded enums plus real outcome metrics give the predictor better-grounded features.
