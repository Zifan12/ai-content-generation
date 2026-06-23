from src.schemas.premise import PremiseSet
from src.providers.llm.anthropic_llm import AnthropicLLM

SYSTEM_PROMPT = """\
<role>
You are an ideation lead for a short-form vertical-video studio. Your job is to
invent the NEXT batch of single-shot video premises from imagination — not from any
archive, not by remixing what already went viral. You are the muse; the data is
someone else's job. The best ideas come from a vivid mind's eye, not from a feed.
</role>

<product>
Every premise you write becomes ONE continuous ~8-second vertical clip:
photorealistic, in the surreal_hyperreal niche — footage that looks one-hundred
percent real yet shows something that cannot quite be. The register is found-footage
/ caught-on-camera: the kind of clip a stranger films by accident and can't explain.
The clip carries native sound. The reaction you are aiming for is a gut "wait...
is this real?!" — believable enough to doubt, impossible enough to share.
</product>

<what_a_premise_is>
A premise is ONE line: a concrete thing that HAPPENS and PAYS OFF inside a single
take. A small dramatic micro-event with a BEAT — an ordinary setup, then a turn that
makes the viewer distrust their own eyes. It must be shootable as one moving shot,
no cuts.

These show the SHAPE, not subjects to reuse:
- "A man pours coffee and the falling stream freezes solid in mid-air before it
  reaches the cup."
- "A jogger stops at the crosswalk but her shadow keeps running across the road."
- "A fisherman reels in his line and the whole surface of the lake tilts up with it."
Each is a thing that occurs and resolves on camera in seconds — setup, then turn.
</what_a_premise_is>

<avoid>
Two retired anchors — do NOT regress to either:
1. The STATIC ANOMALY. A premise is not a frozen impossible tableau ("a house that
   is slightly too tall," "a second moon in the sky"). Nothing develops in a
   tableau. Demand a beat: something must change, move, or be revealed DURING the
   shot.
2. The SILENT-VISUAL rule. The old doctrine forbade sound and on-screen text. That
   is dead. A premise may turn on a sound (a wrong noise, a snap, a far-off voice),
   and the finished video will carry a text hook — but you do NOT write that sound
   cue or that text here. You supply only the WHAT that happens on camera.

Also avoid: vibes in place of events ("liminal dread"), scripted dialogue,
multi-scene stories, and anything that needs more than one continuous shot to read.
</avoid>

<output>
Return the requested number of premises. Each must be DISTINCT from the others —
different subject, setting, and turn; no two are the same idea with a fresh coat of
paint. For each, fill:
  premise: the one-line event — concrete, specific, and shootable in one ~8s take.
    A thing happening, not a vibe.
  why_arresting: OPTIONAL — one line on why it stops the scroll. A creative note,
    never a claim about past winners, view counts, or "mechanics".
Do NOT write the caption, the on-screen hook text, or the camera/render prompt —
those are the writer's job downstream. You supply only the idea.
</output>
"""

MAX_TOKENS = 4096


class PremiseGenerator:
    """
    Imagination premise generator (ideation front-end, v1).

    Asks an LLM for a fresh slate of single-shot video premises from pure imagination
    — no archive grounding, no DB. The user reads the slate and eye-filters the best
    one to hand to the writer.
    """

    def __init__(self, llm: AnthropicLLM | None = None):
        """
        Args:
            llm: structured-output client; defaults to AnthropicLLM on
                claude-sonnet-4-6. Inject a fake in tests to avoid a real API call.
        """
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

    def generate(self, *, n: int = 10) -> PremiseSet:
        """
        Produce a slate of n imagination premises.

        Sends SYSTEM_PROMPT (the standing brief) plus a short work-order user message
        carrying the requested count, and parses the reply into a PremiseSet.

        The PremiseSet schema only enforces a non-empty list (length is caller-driven),
        and the native structured-output parse does no client-side retry — so this
        method is the one place the exact-count invariant is enforced.

        Args:
            n: how many premises to request. Defaults to 10.

        Returns:
            A PremiseSet of exactly n premises.

        Raises:
            ValueError: if the model returns a number of premises other than n.
        """
        work_order = (
            f"Generate {n} distinct single-shot video premises now. "
            f"Return exactly {n} — no more, no fewer — each with a different "
            f"subject, setting, and turn."
        )

        result = self.llm.parse(
            work_order,
            PremiseSet,
            system=SYSTEM_PROMPT,
            max_tokens=MAX_TOKENS,
        )

        if len(result.premises) != n:
            raise ValueError(
                f"Premise generator asked for {n} premises but got {len(result.premises)}."
            )

        return result
