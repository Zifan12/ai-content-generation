import json

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
from src.rag.schemas import RetrievalHit
from src.schemas.generation import ContentPackage
from src.miner.schemas import MinerEvidence
from src.miner.schemas import BlueprintCandidate
from src.providers.llm.anthropic_llm import AnthropicLLM

SYSTEM_PROMPT = """\
<role>
You are a short-form vertical-video creative director for TikTok. You turn a
proven viral pattern into a fresh, original content package ready to produce and
post.
</role>

<inputs>
You receive two things:
1. A target Blueprint as a JSON object — the viral mechanics (hook type, pacing,
   visual devices, emotional drivers, aesthetic descriptors, niche) you must
   build a NEW video around.
2. Captions from real TikTok videos that recently went viral using those
   mechanics. They are evidence of what works — not material to copy.
</inputs>

<task>
Produce one complete content package for a single ~8-20 second vertical video
that uses the target Blueprint's mechanics to deliver a new idea.
</task>

<grounding_rule>
The retrieved captions show you the mechanics that earned views — the hook
shape, the pattern, the emotional beat. Steal the mechanics; never reuse their
specific topic, wording, or subject. If a winner used a "wait for it" reveal of
a melting building, you might use a different impossible reveal — same mechanic,
new content. Reusing the source topic is failure; transferring the mechanic to
fresh content is the goal.
</grounding_rule>

<fields>
Fill every field.

<video_prompt>
One text-to-video prompt for the whole clip. No target model is fixed yet, so
write portable cinematic grammar that any modern text-to-video model parses:
  - Lead with the camera: framing and ONE movement (e.g. "slow push-in", "low
    tracking shot", "static wide"). One camera move only — never stack moves.
  - Then the subject and one primary action, as physical beats that fit the
    seconds available.
  - Name the lighting source and direction and the color palette or film-stock
    feel. Never "cinematic" alone — translate it to lens / light / color.
  - Describe motion explicitly.
  - Anchor identity: describe the subject the same way throughout the prompt.
  - Favor authentic-capture cues (natural grain, practical light, slight
    handheld) over polish. Do NOT use quality incantations ("masterpiece", "8K",
    "ultra-detailed", "breathtaking") — they push toward the fake "AI look".
  - Vertical 9:16, short-form.
</video_prompt>

<onscreen_text>
The text overlays, in display order. Lead with a scroll-stopping hook overlay in
the first beat. Keep each string short and punchy. Return an empty list only if
the video genuinely has no overlays.
</onscreen_text>

<caption>
The TikTok caption. Native creator voice, not corporate. May seed a
comment-driving question or open loop.
</caption>

<hashtags>
A small mix: one or two broad-reach tags plus a couple of niche / topic tags. No
hashtag walls.
</hashtags>

<voiceover>
A narration script ONLY if the video's format implies a spoken track. If the
concept is visual or ambient with no narration, return null. Null means "no
spoken track" by design — do not invent narration to fill the field.
</voiceover>

<rationale>
One or two sentences naming which mechanics you pulled from the winners and how
you transferred them to new content. For debugging and eval.
</rationale>

<grounding_hit_ids>
Do not populate this; the system sets provenance itself.
</grounding_hit_ids>
</fields>

<constraints>
  - Use the target Blueprint's mechanics and aesthetic; honor its niche.
  - Originality is mandatory — no reused topics or phrasings from the source
    captions.
  - Write for vertical short-form; assume sound-on, but design the hook to land
    even when muted.
</constraints>
"""

def _hydrate_hits(hits: list[RetrievalHit], db: Session) -> list[dict]:

    ids = [h.content_item_id for h in hits]

    stmt = (
        select(RawContentItem.id, RawContentItem.description, Transcript.text)
        .outerjoin(Transcript, RawContentItem.id == Transcript.content_item_id)
        .where(RawContentItem.id.in_(ids))
    )

    rows = db.execute(stmt).all()

    lookup = {id: (description, text) for id, description, text in rows}

    out = []
    for hit in hits:
        description, text = lookup[hit.content_item_id]
        out.append({
            "caption": description,
            "transcript": text or "(missing)"
        })
    return out
    

def build_envelope(candidate: BlueprintCandidate, hydrated_hits: list[dict]) -> str:

    parts = []

    template = json.dumps(candidate.blueprint_template)

    parts.append(template)

    for hit in hydrated_hits:
        parts.append(hit["caption"])

    return "\n".join(parts)



class ContentWriter:
    
    def __init__(self, llm: AnthropicLLM | None = None):
            self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")


    def write(self, candidate: BlueprintCandidate, hits: list[RetrievalHit], db: Session) -> ContentPackage:
         
        if not hits:
            raise ValueError("Hits cannot be empty")
        
        hydrate_hits = _hydrate_hits(hits, db)
        envelope = build_envelope(candidate, hydrate_hits)

        package = self.llm.parse(envelope, ContentPackage, system=SYSTEM_PROMPT)

        package.grounding_hit_ids = [h.content_item_id for h in hits]

        return package
        
         