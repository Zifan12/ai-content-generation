"""
Pydantic contracts for the imagination premise generator (ideation front-end).

The premise generator asks an LLM to propose fresh one-line premises — believable
dramatic micro-events a viewer might ask "is this real?!" about. No archive grounding
in v1: the user reads a slate and eye-filters the best one to feed the writer.
The slate size is set by the caller (n); the schema only requires at least one premise.

These models are the validated shape that LLM call must return (via AnthropicLLM.parse).

Premise is one proposed idea; PremiseSet wraps a variable-length list of them.
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
    A variable-length list of proposed premises — the full output of one generation call.

    Length is driven by the caller's n (not fixed in the schema). min_length=1 rejects
    empty slates at parse time. If the LLM returns fewer or more than requested, the
    caller should retry or validate count in application code.
    """

    model_config = ConfigDict(extra="forbid")

    premises: list[Premise] = Field(min_length=1)
