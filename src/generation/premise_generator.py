import json

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.models.trend import RawContentItem
from src.models.niche import Niche
from src.schemas.premise import PremiseSet
from src.miner.schemas import BlueprintCandidate
from src.providers.llm.anthropic_llm import AnthropicLLM

SYSTEM_PROMPT = """\
<role>
You are an ideation lead for a short-form vertical-video studio. You read what
already went viral in one niche and propose the NEXT batch of ideas to make —
fresh subjects built on the proven engines, never reruns of what already won.
</role>

<inputs>
You receive two things:
1. A slate of real TikTok videos that recently went viral in this niche. Each is
   given by its on-screen description, its hashtags, and its view count. This is
   the EVIDENCE — proof of what earned attention, not a catalog to copy.
2. A mechanics recipe: the recurring combination of viral devices the miner found
   clustering across these winners. This is the abstract ENGINE the slate shares.
</inputs>

<task>
First, INFER THE MECHANIC behind the winners — the repeatable engine, stated
abstractly, independent of any one video's subject. In this niche the engines
look like: uncanny-domestic (an ordinary home scene tilted into the impossible),
inescapable-loop (a moment that cannot resolve and keeps returning),
liminal-breach (a familiar space opening onto somewhere it should not),
perceptual-doubt (the eye is shown something it cannot trust). Name the engine in
your own words — these are examples, not a fixed list.

Then PROPOSE EXACTLY FIVE fresh premises. Each one reuses a proven engine but runs
it on a BRAND-NEW SUBJECT the winners never touched. A premise is one line: the
single WHAT a video will be built around ("a man's reflection keeps aging while he
does not"). It is a subject and a situation, not a script.
</task>

<grounding_rule>
This is the rule the whole job turns on: STEAL THE ENGINE, NEVER THE SUBJECT. If a
winner got views from a melting staircase, you may reuse its liminal-breach engine
— but your premise must be a different thing entirely (a doorway, a tide, a face),
never another staircase. Reusing a winner's subject, setting, or specific image is
failure. Transferring its abstract engine onto an unrelated subject is the entire
point. When in doubt, ask: "could a viewer who saw the winner recognize my premise
as the same video?" If yes, you copied — discard it and move further.
</grounding_rule>

<format>
This niche is SILENT-VISUAL surreal_hyperreal: photoreal footage of impossible or
uncanny things, carried entirely by the image. No dialogue, no voiceover, no
narration, no text-on-screen gag. The premise must land MUTED — the wrongness has
to be SEEN, not said. A premise that only works if someone explains it is wrong for
this niche. Favor premises that are photorealistic in texture but impossible in
fact: the uncanny lives in the gap between "looks completely real" and "cannot be
real".
</format>

<output>
Return exactly five premises. For each, fill all three fields:
  premise: the one-line subject + situation. Concrete, specific, shootable. Not a
    vibe ("liminal dread") — a thing happening ("an empty playground swing keeps
    moving as the others stop").
  winning_mechanics: name the engine this premise echoes, abstractly, and say which
    winner(s) on the slate run that same engine. This forces you to ground the idea
    in real evidence, not invent in a vacuum.
  copies_nothing: justify how this premise's SUBJECT differs from every winner it
    drew on. Do not assert "it's original" — articulate the divergence (different
    object, different setting, different reveal). If you cannot name a concrete
    difference, the premise is too close; replace it.

Five distinct subjects, distinct from each other and from every winner. No two of
your five may share the same subject with a different coat of paint.
</output>
"""

def _top_winners(db: Session, niche: str, k) -> list[RawContentItem]:
    
    stmt = (
        select(RawContentItem)
        .join(Niche, RawContentItem.niche_id == Niche.id)
        .where(Niche.name == niche)
        .order_by(RawContentItem.views.desc())
        .limit(k)
    )

    return list(db.execute(stmt).scalars().all())

def build_envelope(winners: list[RawContentItem], candidate: BlueprintCandidate) -> str:
    """
    Compose the user-message string for one premise-generation call.

    This is a pure formatter: it lays the per-call payload on screen exactly as the
    SYSTEM_PROMPT's <inputs> block promises the model — a slate of real winners and a
    mechanics recipe. No DB access, no LLM call, no side effects.

    Args:
        winners: the top-by-views RawContentItem rows for this niche (from
            _top_winners). Each contributes a labeled block carrying its description,
            hashtags, and view count — the EVIDENCE the model grounds fresh premises on.
        candidate: the miner's ranked mechanic combo; its blueprint_template (the
            signal-only field dict) is serialized as the abstract mechanics RECIPE.

    Returns:
        A single string: the recipe first, then one labeled block per winner. Joined
        with blank lines so the model reads it as distinct sections.
    """
    parts = []

    recipe = json.dumps(candidate.blueprint_template)
    parts.append(f"Mechanics recipe (the recurring engine across these winners):\n{recipe}")

    for i, winner in enumerate(winners, 1):
        description = winner.description if winner.description else "n/a"
        tags = [tag for tag in (winner.hashtags or []) if tag]
        hashtags = ", ".join(tags) if tags else "n/a"

        lines = [
            f"Winner {i} — a real video that went viral in this niche:",
            f"Description: {description}",
            f"Hashtags: {hashtags}",
            f"Views: {winner.views:,}",
        ]
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


class PremiseGenerator:

    def __init__(self, llm: AnthropicLLM | None = None):
        
            self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

    def generate(self, candidate: BlueprintCandidate, db: Session, niche: str, k: int=5) -> PremiseSet:
         
        winners = _top_winners(db, niche, k)

        if not winners:
            raise ValueError

        envelope = build_envelope(winners, candidate)

        premises = self.llm.parse(envelope, PremiseSet, system=SYSTEM_PROMPT, max_tokens=4096)
         
        return premises
