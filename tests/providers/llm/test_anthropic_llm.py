"""Tests for AnthropicLLM.parse() — mocked client, no live API calls."""
import sys
from unittest.mock import MagicMock

# Patch langfuse before importing the module under test
_mock_langfuse = MagicMock()
_mock_langfuse.observe = lambda **kwargs: (lambda fn: fn)
sys.modules["langfuse"] = _mock_langfuse

import pytest  # noqa: E402
from anthropic import BadRequestError  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from src.providers.llm.anthropic_llm import AnthropicLLM, TruncatedResponseError  # noqa: E402
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
        "cache_control": {"type": "ephemeral", "ttl": "5m"},
    }]


def test_parse_cache_ttl_override():
    """A constructor cache_ttl overrides the 5m default in the system block."""
    expected = SimpleOutput(answer="ok", score=0.5)
    llm = AnthropicLLM(cache_ttl="1h")
    llm.client = MagicMock()
    llm.client.messages.parse.return_value = make_mock_response(expected)

    llm.parse(prompt="hi", response_model=SimpleOutput, system="sys")

    call_kwargs = llm.client.messages.parse.call_args.kwargs
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_parse_raises_named_error_on_max_tokens_truncation():
    """stop_reason == "max_tokens" must raise TruncatedResponseError naming the
    fix (per-caller max_tokens), instead of surfacing truncated JSON as a
    cryptic validation error — the twice-bitten failure class."""
    llm = AnthropicLLM()
    llm.client = MagicMock()
    response = make_mock_response(SimpleOutput(answer="cut", score=0.1))
    response.stop_reason = "max_tokens"
    llm.client.messages.parse.return_value = response

    with pytest.raises(TruncatedResponseError, match="max_tokens=1024"):
        llm.parse(prompt="hi", response_model=SimpleOutput)


def test_parse_retries_grammar_compilation_timeout():
    """The grammar-timeout 400 (transient server-side, BUG-007) is retried;
    the call succeeds on the second attempt without surfacing the error."""
    expected = SimpleOutput(answer="ok", score=0.5)
    grammar_error = BadRequestError(
        message="Grammar compilation timed out.",
        response=MagicMock(status_code=400),
        body={"type": "error", "error": {"message": "Grammar compilation timed out."}},
    )
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.side_effect = [grammar_error, make_mock_response(expected)]

    result = llm.parse(prompt="hi", response_model=SimpleOutput)

    assert result == expected
    assert llm.client.messages.parse.call_count == 2


def test_parse_does_not_retry_other_400s():
    """Any other BadRequestError raises immediately — only the grammar-timeout
    message is treated as transient."""
    other_error = BadRequestError(
        message="max_tokens: must be positive",
        response=MagicMock(status_code=400),
        body={"type": "error", "error": {"message": "max_tokens: must be positive"}},
    )
    llm = AnthropicLLM()
    llm.client = MagicMock()
    llm.client.messages.parse.side_effect = other_error

    with pytest.raises(BadRequestError):
        llm.parse(prompt="hi", response_model=SimpleOutput)

    assert llm.client.messages.parse.call_count == 1


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
