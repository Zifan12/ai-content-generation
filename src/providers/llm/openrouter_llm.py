"""
OpenRouter wrapper exposing the same structured-output ``parse`` interface as
``AnthropicLLM``, so any pipeline seat can swap providers via constructor
injection with no component changes.

Transport is the ``openai`` SDK pointed at OpenRouter's OpenAI-compatible
endpoint. The critical difference from the Anthropic wrapper: Anthropic's
``messages.parse`` enforces the schema SERVER-SIDE (invalid JSON is
impossible), while OpenRouter's ``response_format: json_schema`` enforcement
is provider/model-dependent. Defense here is layered (decisions ratified
2026-07-02, plan Task 2 forks F1-F3):

- F2: request ``strict: true`` json_schema AND ``provider.require_parameters``
  (routing refuses providers that would silently ignore the schema), AND
  validate client-side anyway.
- F1: on client-side validation failure, retry up to ``_VALIDATION_RETRIES``
  times, feeding the validation error back to the model; exhaustion raises
  ``SchemaValidationExhaustedError`` (loud, names model + schema — a cheap
  model failing loudly is the desired promotion-gate behavior).
- F3: no bespoke transport retries — the openai SDK already retries 429/5xx/
  connection errors natively (max_retries default 2), mirroring the Anthropic
  SDK posture. Add custom retries only after a documented incident (the
  grammar-timeout lesson, BUG-007).
"""

import logging
import os
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from src.observability.tracing import traced
from src.providers.llm.anthropic_llm import TruncatedResponseError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# F1: initial attempt + this many corrective retries, then raise.
_VALIDATION_RETRIES = 2


# JSON-schema constraint keywords stripped from the WIRE schema before sending.
# Providers reached through OpenRouter's output_config translation reject them
# (live 400, 2026-07-02: Anthropic/Bedrock/Azure all refused 'maxItems' for an
# array — emitted by any Pydantic list field with max_length). Stripping is
# safe: the full Pydantic model still validates the response client-side, and
# violations enter the corrective-retry loop.
_UNSUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "maxItems",
        "minItems",
        "maxLength",
        "minLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "uniqueItems",
    }
)


def _sanitize_schema(node, *, in_properties: bool = False):
    """Recursively drop constraint keywords providers reject from a JSON schema.

    Returns a new structure; the input is not mutated. Keys directly inside a
    "properties" (or "$defs"/"definitions") map are FIELD NAMES, not schema
    keywords — a field literally named "pattern" or "format" must survive, so
    those maps keep every key and only their values are sanitized.
    """
    if isinstance(node, dict):
        sanitized = {}
        for key, value in node.items():
            if not in_properties and key in _UNSUPPORTED_SCHEMA_KEYWORDS:
                continue
            child_is_properties = not in_properties and key in (
                "properties",
                "$defs",
                "definitions",
            )
            sanitized[key] = _sanitize_schema(value, in_properties=child_is_properties)
        return sanitized
    if isinstance(node, list):
        return [_sanitize_schema(item) for item in node]
    return node


class SchemaValidationExhaustedError(RuntimeError):
    """The model kept returning schema-invalid JSON after all corrective retries.

    Raised instead of surfacing a raw pydantic ValidationError so the failure
    names the model and seat-relevant context. For a cheap-fleet seat this is
    the promotion gate doing its job: the fix is the providers.yaml rollback
    (one line back to the sonnet model), not a code change.
    """


class OpenRouterLLM:
    """
    Wraps OpenRouter chat completions with schema-validated structured output.

    Public interface is contract-identical to ``AnthropicLLM``: ``parse()``
    returns the validated Pydantic object; ``parse_with_raw()`` additionally
    returns a raw-meta dict with the SAME keys (cache counters are ``None`` —
    OpenRouter does not report Anthropic-style cache usage on this path).
    """

    def __init__(
        self,
        model: str,
        *,
        timeout_seconds: float = 300.0,
        client=None,
    ):
        """
        Args:
            model: OpenRouter model id (e.g. ``google/gemini-2.5-flash-lite``,
                ``anthropic/claude-sonnet-5``).
            timeout_seconds: Per-request client timeout; 300s mirrors
                ``AnthropicLLM`` (clears the slowest legitimate call while not
                letting an unattended pipeline hang for the SDK's long default).
            client: Test seam — an object with ``chat.completions.create``.
                When ``None``, a real openai SDK client is built against
                OpenRouter using the ``OPENROUTER_API_KEY`` env var (loaded
                from config/.env by callers); missing key fails loud here
                rather than as a cryptic 401 later.
        """
        self.model = model
        if client is None:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY is not set — needed by OpenRouterLLM. "
                    "Put it in config/.env."
                )
            from openai import OpenAI

            client = OpenAI(
                base_url=_OPENROUTER_BASE_URL,
                api_key=api_key,
                timeout=timeout_seconds,
            )
        self.client = client

    @traced(name="openrouter_llm.parse", kind="generation")
    def parse_with_raw(
        self,
        prompt: str,
        response_model: Type[T],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> tuple[T, dict]:
        """
        Run the model on ``prompt``; return (validated instance, raw-meta dict).

        The request pins ``json_schema`` output with ``strict: true`` and
        restricts provider routing to providers that honor the parameters
        (``require_parameters``). The response is still validated client-side;
        schema-invalid JSON triggers the F1 corrective-retry loop.

        Returns:
            Tuple of (parsed_model, raw_meta) where raw_meta keys match
            ``AnthropicLLM.parse_with_raw`` exactly:
              - "raw_response": dict from ``parsed.model_dump()``
              - "usage_input_tokens" / "usage_output_tokens": int
              - "usage_cache_read_tokens" / "usage_cache_write_tokens": None
                (not reported on this path)

        Raises:
            TruncatedResponseError: response hit max_tokens before completing
                (``finish_reason == "length"``) — raise THAT call site's
                max_tokens, never a shared default.
            SchemaValidationExhaustedError: schema-invalid JSON persisted
                through all corrective retries.
        """
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {}
        if temperature is not None:
            kwargs["temperature"] = temperature

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "strict": True,
                "schema": _sanitize_schema(response_model.model_json_schema()),
            },
        }

        attempts_left = _VALIDATION_RETRIES
        while True:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                response_format=response_format,
                extra_body={"provider": {"require_parameters": True}},
                **kwargs,
            )

            choice = completion.choices[0]
            # Truncation checked BEFORE validation: a response cut off at
            # max_tokens carries incomplete JSON, and surfacing that as a
            # validation error hides the real cause (same guard as the
            # Anthropic wrapper's TruncatedResponseError).
            if choice.finish_reason == "length":
                raise TruncatedResponseError(
                    f"Response hit max_tokens={max_tokens} before completing "
                    f"({response_model.__name__}, model={self.model}). Raise THIS "
                    f"call site's max_tokens (per-caller override, not the shared default)."
                )

            content = choice.message.content or ""
            try:
                parsed = response_model.model_validate_json(content)
                break
            except ValidationError as e:
                if attempts_left <= 0:
                    raise SchemaValidationExhaustedError(
                        f"Model {self.model} returned schema-invalid JSON for "
                        f"{response_model.__name__} after "
                        f"{_VALIDATION_RETRIES} corrective retries. Last "
                        f"validation error: {e}"
                    ) from e
                attempts_left -= 1
                # F1: feed the failure back — assistant turn with the bad
                # output, user turn naming the validation error.
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Your previous response failed schema validation: "
                            f"{e}. Return ONLY the corrected JSON object "
                            "matching the schema — no prose."
                        ),
                    },
                ]

        raw = {
            "raw_response": parsed.model_dump(),
            "usage_input_tokens": completion.usage.prompt_tokens,
            "usage_output_tokens": completion.usage.completion_tokens,
            "usage_cache_read_tokens": None,
            "usage_cache_write_tokens": None,
        }

        # Same one-line local usage record as AnthropicLLM (BUG-001: never
        # depend on the dashboard alone for spend truth).
        logger.info(
            "llm.parse model=%s schema=%s in=%s out=%s cache_read=%s cache_write=%s",
            self.model,
            response_model.__name__,
            raw["usage_input_tokens"],
            raw["usage_output_tokens"],
            raw["usage_cache_read_tokens"],
            raw["usage_cache_write_tokens"],
        )

        return parsed, raw

    def parse(
        self,
        prompt: str,
        response_model: Type[T],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> T:
        """
        Run the model on ``prompt``; return a validated ``response_model`` instance.

        Same call as ``parse_with_raw`` with the raw-meta dict discarded —
        for callers that don't need usage counters.
        """
        return self.parse_with_raw(prompt, response_model, system, max_tokens, temperature)[0]
