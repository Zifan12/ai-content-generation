"""
Anthropic API token pricing and cost computation.

Single source of truth for per-token rates and per-call cost calculation.
Used by:
  - scripts/extractor_cost_report.py (historical reporting + dry-run estimation)
  - src/scrapers/recurring.py (per-call spend tracking for budget guard)

Update PRICE_PER_M_TOKENS if Anthropic changes pricing or a new model is introduced.
"""

from src.models.extractor_response import ExtractorResponse


PRICE_PER_M_TOKENS = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 6.00,  # 1-hour TTL
    "cache_read": 0.30,
}


def cost(tokens: int | None, price_per_m: float) -> float:
    """
    Return dollar cost for ``tokens`` at the given per-million rate.

    Treats None as 0 so callers do not need to null-check token fields
    (Anthropic responses may omit any usage bucket).

    Args:
        tokens: Token count or None.
        price_per_m: Price per million tokens in USD.

    Returns:
        Dollar cost as a float.
    """
    return (tokens or 0) / 1_000_000 * price_per_m


def compute_response_cost(resp: ExtractorResponse) -> float:
    """
    Compute total USD cost of a single ExtractorResponse row.

    Sums all four token buckets (input, output, cache_read, cache_write)
    at their respective per-million rates. Missing buckets contribute 0.

    Args:
        resp: ExtractorResponse row with usage_* token columns populated.

    Returns:
        Total dollar cost of the LLM call as a float.
    """
    return (
        cost(resp.usage_input_tokens, PRICE_PER_M_TOKENS["input"])
        + cost(resp.usage_output_tokens, PRICE_PER_M_TOKENS["output"])
        + cost(resp.usage_cache_read_tokens, PRICE_PER_M_TOKENS["cache_read"])
        + cost(resp.usage_cache_write_tokens, PRICE_PER_M_TOKENS["cache_write"])
    )
