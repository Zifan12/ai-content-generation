"""
Pydantic contracts for the imagination premise generator (ideation front-end).

The premise generator asks an LLM to propose fresh one-line premises — believable
dramatic micro-events a viewer might ask "is this real?!" about. No archive grounding
in v1: the user reads a slate of ten and eye-filters the best one to feed the writer.

These models are the validated shape that LLM call must return (via AnthropicLLM.parse).

Premise is one proposed idea; PremiseSet wraps exactly ten of them.
"""

from pydantic import BaseModel, ConfigDict, Field


class Premise(BaseModel):
    """
    One proposed content premise from pure imagination.

    Fields:
      premise: the one-line content idea — a thing happening, shootable in one ~8s take
        ("a man's coffee stream freezes mid-pour in a normal kitchen"). This is the WHAT
        the writer will develop into a video.
      why_arresting: optional creative note on why this premise stops the scroll. NOT a
        grounding claim — no reference to archive winners or viral mechanics.

    min_length on premise is only a junk filter (reject empty/trivial strings); real
    quality control lives in the generator's system prompt and the human eye-gate.
    """

    model_config = ConfigDict(extra="forbid")

    premise: str = Field(min_length=10)
    why_arresting: str | None = None


class PremiseSet(BaseModel):
    """
    Exactly ten proposed premises — the full output of one generation call.

    The list is length-locked to 10 (min_length == max_length): the user reads a fixed
    slate and picks one. If the LLM returns 9 or 11, validation fails at parse time and
    the caller can retry, rather than silently accepting a short or bloated set.
    """

    model_config = ConfigDict(extra="forbid")

    premises: list[Premise] = Field(min_length=10, max_length=10)
