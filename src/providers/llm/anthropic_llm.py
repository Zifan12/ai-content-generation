from anthropic import Anthropic
from pydantic import BaseModel
from typing import TypeVar, Type
from src.observability.tracing import traced

T = TypeVar("T", bound=BaseModel)

class AnthropicLLM:
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
        response = self.client.messages.parse(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            output_format=response_model,
            **({"system": system} if system is not None else {}),
        )
        return response.parsed_output

        
        