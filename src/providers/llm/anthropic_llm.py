"""
Anthropic SDK wrapper exposing structured-output `parse`.

Centralizes model selection, system prompt plumbing, and Langfuse tracing so
every caller gets identical observability and identical retry/timeout
behavior.
"""

from anthropic import Anthropic
from pydantic import BaseModel
from typing import TypeVar, Type
from src.observability.tracing import traced

T = TypeVar("T", bound=BaseModel)

class AnthropicLLM:
    """
    Wraps Anthropic SDK messages.parse with tracing, caching, and raw-response capture.

    parse_with_raw() is the primary method — it returns both the validated Pydantic
    object and raw usage metadata for cost tracking. parse() delegates to it and
    discards the metadata for callers that don't need it.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model
        self.client = Anthropic()

    @traced(name="anthropic_llm.parse", kind="generation")
    def parse_with_raw(
        self,
        prompt: str,
        response_model: Type[T],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> tuple[T, dict]:
        """
        Run model on prompt; return parsed Pydantic instance plus a raw-response
        dict suitable for caching and later re-parsing under a new schema version.

        Same wire call as `parse()` — the only difference is that this method
        surfaces the model's raw output dict and token-usage counters alongside
        the validated Pydantic object, instead of discarding them.

        Args:
            prompt: User input text.
            response_model: Pydantic BaseModel class to parse response into.
            system: Optional system prompt (instructions for the model).
            max_tokens: Max tokens to generate (default 1024).
            temperature: Optional sampling temperature. When None (default) the
                param is omitted from the API call. Only valid on models that
                still accept sampling params (e.g. Sonnet); Opus 4.7+ removed
                temperature/top_p/top_k and returns 400 if sent.

        Returns:
            Tuple of (parsed_model, raw_meta), where raw_meta is a JSON-serializable
            dict with keys:
              - "raw_response": dict from `parsed_output.model_dump()`
              - "usage_input_tokens": int
              - "usage_output_tokens": int
              - "usage_cache_read_tokens": int | None (None if cache not used)
        """

        if system is not None:
            system_param = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
            kwargs = {"system": system_param}
        else:
            kwargs = {}

        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self.client.messages.parse(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            output_format=response_model,
            **kwargs,
        )

        parsed = response.parsed_output
        raw = {
            "raw_response": response.parsed_output.model_dump(),
            "usage_input_tokens": response.usage.input_tokens,
            "usage_output_tokens": response.usage.output_tokens,
            "usage_cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", None),
            "usage_cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", None),
        }

        return parsed, raw

    def parse(self,
              prompt: str,
              response_model: Type[T],
              system: str | None = None,
              max_tokens: int=1024,
              temperature: float | None = None,
    ) -> T:
        """
        Run model on prompt; return Pydantic instance of `response_model`.

        Uses Anthropic's native structured-output `messages.parse` API, which
        enforces `response_model` schema server-side (no client-side retries needed).
        This ensures deterministic, type-safe LLM outputs for judges, extractors, etc.
        
        Args:
            prompt: user input text
            response_model: Pydantic BaseModel class to parse response into
            system: optional system prompt (instructions for the model)
            max_tokens: max tokens to generate (default 1024)
            temperature: optional sampling temperature; None omits the param.
                Opus 4.7+ rejects sampling params (400) — leave None there.
        
        Returns:
            Instance of response_model, guaranteed to match schema.
        """
        return self.parse_with_raw(prompt, response_model, system, max_tokens, temperature)[0]

        
        