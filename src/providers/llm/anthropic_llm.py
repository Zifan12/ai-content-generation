"""
Anthropic SDK wrapper exposing structured-output `parse`.

Centralizes model selection, system prompt plumbing, and Langfuse tracing so
every caller gets identical observability and identical retry/timeout
behavior.
"""

import logging
import time

from anthropic import Anthropic, BadRequestError
from pydantic import BaseModel
from typing import Any, TypeVar, Type
from src.observability.tracing import get_client, traced

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class TruncatedResponseError(RuntimeError):
    """The model hit max_tokens before finishing the structured response.

    Raised instead of letting a truncated JSON surface as a cryptic
    validation/parse error — this failure class has bitten twice (writer
    chain packages at the shared 1024 default; context-agent finalize).
    The fix is always per-caller: raise THAT call site's max_tokens (the
    WRITER_MAX_TOKENS / _FINALIZE_MAX_TOKENS pattern), never the shared
    default.
    """

# "Grammar compilation timed out" is a transient server-side failure of the
# structured-output constrained-decoding compiler, surfaced (misleadingly) as a
# 400 invalid_request_error. The grammar is cached server-side once a compile
# succeeds, so a short retry usually clears it. Seen live 2026-07-01 killing a
# paid pitch run on the trivial one-bool DedupVerdict schema (BUG-007).
_GRAMMAR_TIMEOUT_MARKER = "Grammar compilation timed out"
_GRAMMAR_TIMEOUT_RETRIES = 2
_GRAMMAR_TIMEOUT_BACKOFF_SECONDS = 2.0

class AnthropicLLM:
    """
    Wraps Anthropic SDK messages.parse with tracing, caching, and raw-response capture.

    parse_with_raw() is the primary method — it returns both the validated Pydantic
    object and raw usage metadata for cost tracking. parse() delegates to it and
    discards the metadata for callers that don't need it.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        *,
        timeout_seconds: float = 300.0,
        cache_ttl: str = "5m",
    ):
        """
        Args:
            model: Anthropic model id every parse call targets.
            timeout_seconds: Explicit per-request client timeout. The SDK's own
                default is 10 minutes — too long for an unattended pipeline to
                sit on one hung call. 300s still clears the slowest legitimate
                call (the 8192-token writer). Transient-retry note: the SDK
                natively retries connection errors, 429s, and 5xx (max_retries
                default 2, exponential backoff) — do not add another layer for
                those here; the only custom retry is the grammar-timeout 400
                in parse_with_raw, which the SDK treats as non-retryable.
            cache_ttl: Prompt-cache TTL for system prompts ("5m" or "1h").
                Default 5m: cache writes bill at a premium (1h writes cost
                2x base input vs 1.25x for 5m) and every pipeline stage that
                reuses a system prompt does so within minutes; a cache hit
                refreshes the TTL, so batch runs stay warm on 5m anyway. Pass
                "1h" only for workloads with genuine >5-minute idle gaps
                between calls sharing one system prompt.
        """
        self.model = model
        self.client = Anthropic(timeout=timeout_seconds)
        self._cache_ttl = cache_ttl

    @traced(
        name="anthropic_llm.parse",
        kind="generation",
        capture_input=False,
        capture_output=False,
    )
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

        # Heterogeneous optional params (system blocks, float temperature) —
        # without the Any annotation mypy locks the dict to the first branch's
        # value type and rejects every later insert and the ** unpack.
        kwargs: dict[str, Any] = {}
        if system is not None:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral", "ttl": self._cache_ttl}}]

        if temperature is not None:
            kwargs["temperature"] = temperature

        # Bounded retry for the one transient failure the SDK reports as a
        # non-retryable 400: grammar-compilation timeout (see module constant).
        # Any other error — real 400s included — propagates on first raise.
        attempts_left = _GRAMMAR_TIMEOUT_RETRIES
        while True:
            try:
                response = self.client.messages.parse(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    output_format=response_model,
                    **kwargs,
                )
                break
            except BadRequestError as e:
                if _GRAMMAR_TIMEOUT_MARKER not in str(e) or attempts_left <= 0:
                    raise
                attempts_left -= 1
                time.sleep(_GRAMMAR_TIMEOUT_BACKOFF_SECONDS)

        # Truncation is checked BEFORE touching parsed_output: a response cut
        # off at max_tokens carries incomplete JSON, and surfacing that as a
        # validation error hides the real cause (see TruncatedResponseError).
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise TruncatedResponseError(
                f"Response hit max_tokens={max_tokens} before completing "
                f"({response_model.__name__}, model={self.model}). Raise THIS "
                f"call site's max_tokens (per-caller override, not the shared default)."
            )

        parsed = response.parsed_output
        # SDK types parsed_output as T | None — None here means the model
        # finished without emitting schema-conformant output (e.g. a refusal).
        # Fail loud with the call's identity rather than deref-crashing.
        if parsed is None:
            raise RuntimeError(
                f"messages.parse returned no parsed_output "
                f"(stop_reason={getattr(response, 'stop_reason', None)!r}, "
                f"schema={response_model.__name__}, model={self.model})"
            )
        raw = {
            "raw_response": parsed.model_dump(),
            "usage_input_tokens": response.usage.input_tokens,
            "usage_output_tokens": response.usage.output_tokens,
            "usage_cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", None),
            "usage_cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", None),
        }

        # Local usage record independent of Langfuse (BUG-001 showed the
        # dashboard can silently mis-record for months) — one line per call.
        logger.info(
            "llm.parse model=%s schema=%s in=%s out=%s cache_read=%s cache_write=%s",
            self.model,
            response_model.__name__,
            raw["usage_input_tokens"],
            raw["usage_output_tokens"],
            raw["usage_cache_read_tokens"],
            raw["usage_cache_write_tokens"],
        )

        # Record a CLEAN input plus usage/model on the Langfuse generation. The
        # decorator's auto-capture is off: it would otherwise serialize
        # response_model (a Pydantic CLASS) as <mappingproxy> garbage. Setting
        # usage/model explicitly keeps both wrapper seats reporting identically
        # rather than relying on SDK auto-recognition (BUG-010).
        get_client().update_current_generation(
            input={"system": system, "prompt": prompt, "schema": response_model.__name__},
            output=raw["raw_response"],
            model=self.model,
            usage_details={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            },
        )

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

        
        