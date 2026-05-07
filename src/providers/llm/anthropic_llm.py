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
    Thin wrapper over Anthropic SDK exposing structured-output `parse`.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model
        self.client = Anthropic()

    @traced(name="anthropic_llm.parse", kind="generation")
    def parse(self,
              prompt: str,
              response_model: Type[T],
              system: str | None = None,
              max_tokens: int=1024,
    ) -> T:
        """
        Run model on prompt; return Pydantic instance of `response_model`.

        Uses Anthropic's structured-output `messages.parse` so response_model
        is enforced server-side rather than via instructor-style retries.
        """
        response = self.client.messages.parse(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            output_format=response_model,
            # Anthropic API rejects system=None on the wire; omit kwarg when unset.
            **({"system": system} if system is not None else {}),
        )
        return response.parsed_output

        
        