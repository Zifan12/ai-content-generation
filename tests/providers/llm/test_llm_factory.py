"""Unit tests for llm_for_seat — all against tmp_path YAML, never the real config."""

import pytest

from src.providers.llm.anthropic_llm import AnthropicLLM
from src.providers.llm.factory import llm_for_seat
from src.providers.llm.openrouter_llm import OpenRouterLLM


def _write_config(tmp_path, body: str):
    path = tmp_path / "providers.yaml"
    path.write_text(body, encoding="utf-8")
    return str(path)


VALID = """
llm:
  gap_agent: {provider: openrouter, model: "google/gemini-2.5-flash-lite"}
  story_craft_gate: {provider: anthropic, model: "claude-sonnet-5"}
"""


def test_openrouter_seat_builds_openrouter_wrapper(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    path = _write_config(tmp_path, VALID)

    llm = llm_for_seat("gap_agent", config_path=path)

    assert isinstance(llm, OpenRouterLLM)
    assert llm.model == "google/gemini-2.5-flash-lite"


def test_anthropic_seat_builds_anthropic_wrapper(tmp_path):
    path = _write_config(tmp_path, VALID)

    llm = llm_for_seat("story_craft_gate", config_path=path)

    assert isinstance(llm, AnthropicLLM)
    assert llm.model == "claude-sonnet-5"


def test_unknown_seat_raises_naming_the_seat(tmp_path):
    path = _write_config(tmp_path, VALID)

    with pytest.raises(RuntimeError, match="nonexistent_seat"):
        llm_for_seat("nonexistent_seat", config_path=path)


def test_missing_llm_block_raises(tmp_path):
    path = _write_config(tmp_path, "video:\n  active: null\n")

    with pytest.raises(RuntimeError, match="llm"):
        llm_for_seat("gap_agent", config_path=path)


def test_unknown_provider_raises(tmp_path):
    path = _write_config(
        tmp_path, 'llm:\n  gap_agent: {provider: closedai, model: "x"}\n'
    )

    with pytest.raises(RuntimeError, match="closedai"):
        llm_for_seat("gap_agent", config_path=path)


def test_openrouter_seat_without_api_key_raises_naming_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = _write_config(tmp_path, VALID)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        llm_for_seat("gap_agent", config_path=path)
