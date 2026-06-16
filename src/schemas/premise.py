"""
Pydantic contracts for the grounded premise generator (ideation front-end).

The premise generator shows an LLM the top-performing videos for a niche (their
descriptions + hashtags) and asks it to propose fresh premises that reuse a proven
viral MECHANIC but use a brand-new SUBJECT — never a direct copy. These models are
the validated shape that LLM call must return (via AnthropicLLM.parse).

Premise is one proposed idea; PremiseSet wraps exactly five of them — the user reads
the set and picks one to feed into the writer.
"""

from pydantic import BaseModel, Field


class Premise(BaseModel):
    """
    One proposed, data-grounded content premise.

    Fields:
      premise: the one-line content idea / subject ("a man's reflection ages while he
        doesn't"). This is the WHAT the writer will develop into a video.
      winning_mechanics: the LLM's stated reason — which proven viral pattern from the
        retrieved winners this premise reuses (e.g. "inescapable-loop dread"). Free-text
        on purpose: there is no validated taxonomy of premise-level mechanics yet (the
        Blueprint enums are a different, lower-level abstraction and will themselves grow
        once the 72K archive is extracted), so the LLM names the pattern in its own words
        and we discover the vocabulary from its outputs.
      copies_nothing: a justification (NOT a bool) explaining how this premise's subject
        differs from every winner it drew on. A bool would be a rubber stamp the model
        always sets true; forcing it to articulate the divergence makes it actually
        diverge, and gives a human something to audit.

    min_length on each field is only a junk filter (reject empty/trivial strings); real
    quality control lives in the generator's system prompt, not here.
    """

    premise: str = Field(min_length=10)
    winning_mechanics: str = Field(min_length=10)
    copies_nothing: str = Field(min_length=10)


class PremiseSet(BaseModel):
    """
    Exactly five proposed premises — the full output of one generation call.

    The list is length-locked to 5 (min_length == max_length): the user is meant to read
    a fixed slate and pick one. If the LLM returns 4 or 6, validation fails at parse time
    and the caller can retry, rather than silently accepting a short or bloated set.
    """

    premises: list[Premise] = Field(min_length=5, max_length=5)
