"""
Seat-based LLM factory: providers.yaml ``llm:`` block -> constructed wrapper.

Every pipeline LLM call site ("seat") is named in config/providers.yaml and
built here, so swapping any seat's provider/model is a YAML edit, not a code
change (closes audit AUD-M21 for the LLM side; spec
docs/superpowers/specs/2026-07-02-openrouter-mixed-fleet-design.md §3.2).

Fail-loud policy (spec §5): unknown seat, missing ``llm:`` block, unknown
provider, or an openrouter seat without OPENROUTER_API_KEY all raise
RuntimeError at construction time — a pipeline must never silently run a
default model.
"""

import yaml

from src.providers.llm.anthropic_llm import AnthropicLLM
from src.providers.llm.openrouter_llm import OpenRouterLLM

_DEFAULT_CONFIG_PATH = "config/providers.yaml"


def llm_for_seat(
    seat: str, config_path: str = _DEFAULT_CONFIG_PATH
) -> AnthropicLLM | OpenRouterLLM:
    """Build the configured LLM wrapper for a named pipeline seat.

    Args:
        seat: Seat name as it appears under the ``llm:`` block — one of
            ``context_agent``, ``idea_fit_gate``, ``gap_agent``,
            ``story_pitcher``, ``story_craft_gate``, ``content_writer``
            (the set is defined by the YAML, not hardcoded here, so adding a
            seat is also config-only plus its call site).
        config_path: Path to the providers YAML; overridable for tests.

    Returns:
        An ``AnthropicLLM`` or ``OpenRouterLLM`` constructed with the seat's
        configured model id.

    Raises:
        RuntimeError: unknown seat, missing ``llm:`` block, or unknown
            provider — message names the offender and the config path.
            (An openrouter seat with OPENROUTER_API_KEY unset raises from
            ``OpenRouterLLM.__init__``, also a RuntimeError naming the var.)
    """
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    llm_block = config.get("llm")
    if not isinstance(llm_block, dict) or not llm_block:
        raise RuntimeError(
            f"No 'llm' seat block in {config_path} — expected a mapping of "
            f"seat -> {{provider, model}}."
        )

    seat_cfg = llm_block.get(seat)
    if seat_cfg is None:
        raise RuntimeError(
            f"Unknown LLM seat {seat!r} — not present under 'llm:' in "
            f"{config_path}. Configured seats: {sorted(llm_block)}."
        )

    provider = seat_cfg.get("provider")
    model = seat_cfg.get("model")
    if not provider or not model:
        raise RuntimeError(
            f"Seat {seat!r} in {config_path} must define both 'provider' and "
            f"'model'; got {seat_cfg!r}."
        )

    if provider == "anthropic":
        return AnthropicLLM(model=model)
    if provider == "openrouter":
        return OpenRouterLLM(model=model)

    raise RuntimeError(
        f"Unknown provider {provider!r} for seat {seat!r} in {config_path} — "
        f"expected 'anthropic' or 'openrouter'."
    )
