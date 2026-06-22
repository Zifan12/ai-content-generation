"""Tests for AnthropicLLM.parse() — mocked client, no live API calls."""
import sys
from unittest.mock import MagicMock

# Patch langfuse before importing the module under test
_mock_langfuse = MagicMock()
_mock_langfuse.observe = lambda **kwargs: (lambda fn: fn)
sys.modules["langfuse"] = _mock_langfuse

from pydantic import BaseModel  # noqa: E402
from src.providers.llm.anthropic_llm import AnthropicLLM  # noqa: E402
from src.schemas.llm import TrendAnalysis, SafetyCheck  # noqa: E402


class SimpleOutput(BaseModel):
    answer: str
    score: float


def make_mock_response(parsed_output):
    """Build a mock response object that mimics client.messages.parse() return."""
    mock_response = MagicMock()
    mock_response.parsed_output = parsed_output
    return mock_response


def test_parse_returns_typed_pydantic_object():
    """parse() should return the exact Pydantic instance from parsed_output."""
    expected = SimpleOutput(answer="yes", score=0.9)
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    result = llm.parse(prompt="test", response_model=SimpleOutput)

    assert isinstance(result, SimpleOutput)
    assert result.answer == "yes"
    assert result.score == 0.9


def test_parse_calls_client_with_correct_params():
    """parse() must call client.messages.parse with output_format= (not response_model=)."""
    expected = SimpleOutput(answer="ok", score=0.5)
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    llm.parse(prompt="hello world", response_model=SimpleOutput, max_tokens=512)

    call_kwargs = llm.client.messages.parse.call_args.kwargs
    assert call_kwargs["output_format"] is SimpleOutput
    assert call_kwargs["max_tokens"] == 512
    assert call_kwargs["messages"] == [{"role": "user", "content": "hello world"}]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


def test_parse_includes_system_when_provided():
    """
    System kwarg must be forwarded as a cache-eligible text block list when not None.

    The block-list shape (vs plain string) is required so the cache_control marker
    can be attached. The Anthropic API silently ignores cache_control on system
    prompts shorter than 1024 tokens; this test does not depend on prompt length.
    """
    expected = SimpleOutput(answer="ok", score=0.5)
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    llm.parse(prompt="hi", response_model=SimpleOutput, system="You are a helpful assistant.")

    call_kwargs = llm.client.messages.parse.call_args.kwargs
    assert call_kwargs["system"] == [{
        "type": "text",
        "text": "You are a helpful assistant.",
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
    }]


def test_parse_omits_system_when_none():
    """system must NOT be passed to client when it is None (Anthropic rejects empty system)."""
    expected = SimpleOutput(answer="ok", score=0.0)
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    llm.parse(prompt="hi", response_model=SimpleOutput)

    call_kwargs = llm.client.messages.parse.call_args.kwargs
    assert "system" not in call_kwargs


def test_parse_works_with_trend_analysis_schema():
    """Verify TrendAnalysis schema passes through parse() correctly."""
    expected = TrendAnalysis(
        virality_score=0.85,
        confidence=0.9,
        trend_stage="emerging",
        reasoning="High velocity hashtag growth",
        signals=["#gymtok +340% in 24h"],
        recommended_hooks=["hot_take", "pain_point"],
    )
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    result = llm.parse(prompt="Analyze this trend", response_model=TrendAnalysis)

    assert isinstance(result, TrendAnalysis)
    assert result.trend_stage == "emerging"
    assert result.virality_score == 0.85


def test_parse_works_with_safety_check_schema():
    """Verify SafetyCheck schema passes through parse() correctly."""
    expected = SafetyCheck(is_safe=True, severity="ok", reason=None, flags=[])
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    result = llm.parse(prompt="Is this content safe?", response_model=SafetyCheck)

    assert isinstance(result, SafetyCheck)
    assert result.is_safe is True
    assert result.severity == "ok"
