"""Unit tests for OpenRouterLLM — all offline via an injected fake client.

The fake stands in for the openai SDK client: it returns queued completion
objects in order and records every request's kwargs, so the tests can assert
on retry behavior (how many calls, what the retry message carried) without
any network or spend.
"""

import pytest
from pydantic import BaseModel

from src.providers.llm.anthropic_llm import TruncatedResponseError
from src.providers.llm.openrouter_llm import (
    OpenRouterLLM,
    SchemaValidationExhaustedError,
)


class Verdict(BaseModel):
    ok: bool
    note: str


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = _Msg(content)
        self.finish_reason = finish_reason


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5


class _Completion:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.choices = [_Choice(content, finish_reason)]
        self.usage = _Usage()


class FakeClient:
    """Returns queued completions in order; records request kwargs."""

    def __init__(self, completions: list[_Completion]) -> None:
        self._queue = list(completions)
        self.requests: list[dict] = []

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.requests.append(kwargs)
                return outer._queue.pop(0)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_parse_valid_json_returns_model():
    fake = FakeClient([_Completion('{"ok": true, "note": "fine"}')])
    llm = OpenRouterLLM(model="test/model", client=fake)

    result = llm.parse("judge this", Verdict)

    assert result == Verdict(ok=True, note="fine")


def test_request_carries_schema_and_provider_routing():
    """The request must ask for json_schema output AND restrict routing to
    providers that honor the parameters (require_parameters), else a provider
    could silently ignore the schema."""
    fake = FakeClient([_Completion('{"ok": true, "note": "fine"}')])
    llm = OpenRouterLLM(model="test/model", client=fake)

    llm.parse("judge this", Verdict, system="you are a judge")

    req = fake.requests[0]
    assert req["response_format"]["type"] == "json_schema"
    assert req["response_format"]["json_schema"]["name"] == "Verdict"
    assert req["extra_body"] == {"provider": {"require_parameters": True}}
    assert req["messages"][0] == {"role": "system", "content": "you are a judge"}
    assert req["messages"][1] == {"role": "user", "content": "judge this"}
    assert "temperature" not in req  # None must be omitted, not sent as null


def test_invalid_json_retries_then_succeeds():
    fake = FakeClient(
        [
            _Completion('{"ok": "not-a-bool"}'),  # fails validation
            _Completion('{"ok": false, "note": "fixed"}'),  # retry succeeds
        ]
    )
    llm = OpenRouterLLM(model="test/model", client=fake)

    result = llm.parse("judge this", Verdict)

    assert result.note == "fixed"
    assert len(fake.requests) == 2
    # The retry message must carry the validation error back to the model.
    retry_messages = fake.requests[1]["messages"]
    assert any("ok" in str(m.get("content", "")) for m in retry_messages[-1:])


def test_exhausted_retries_raises():
    bad = '{"ok": "nope"}'
    fake = FakeClient([_Completion(bad), _Completion(bad), _Completion(bad)])
    llm = OpenRouterLLM(model="test/model", client=fake)

    with pytest.raises(SchemaValidationExhaustedError, match="test/model"):
        llm.parse("judge this", Verdict)

    assert len(fake.requests) == 3  # initial + 2 retries, then loud failure


def test_truncation_raises_truncated_response_error():
    fake = FakeClient([_Completion('{"ok": tr', finish_reason="length")])
    llm = OpenRouterLLM(model="test/model", client=fake)

    with pytest.raises(TruncatedResponseError):
        llm.parse("judge this", Verdict, max_tokens=64)


def test_parse_with_raw_meta_keys_match_anthropic_contract():
    """raw_meta must have the SAME keys as AnthropicLLM.parse_with_raw so
    downstream consumers never branch on provider."""
    fake = FakeClient([_Completion('{"ok": true, "note": "fine"}')])
    llm = OpenRouterLLM(model="test/model", client=fake)

    parsed, raw = llm.parse_with_raw("judge this", Verdict)

    assert parsed.ok is True
    assert set(raw) == {
        "raw_response",
        "usage_input_tokens",
        "usage_output_tokens",
        "usage_cache_read_tokens",
        "usage_cache_write_tokens",
    }
    assert raw["usage_input_tokens"] == 10
    assert raw["usage_output_tokens"] == 5
    assert raw["usage_cache_read_tokens"] is None
