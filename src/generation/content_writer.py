"""
Content writer (P3): turns a premise into a validated single-shot ContentPackage.

ContentWriter.write is model-aware one-pass generation: one structured-output LLM
call produces one ~8s vertical clip's full kit (opening still + motion prompts,
hook text, caption, hashtags). Render dialects from config/render_rules.yaml are
injected into the user prompt so start_keyframe and motion are native to the
chosen image and video models.

Optional RAG grounding (retrieved viral neighbors) supplies aesthetic descriptors,
hook subtype, and transcript when present — never captions (hashtag dumps, not
signal). Imagination-only runs omit hits entirely.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.generation.render_adapters.rules import RenderRules
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
from src.rag.schemas import RetrievalHit
from src.schemas.generation import ContentPackage
from src.providers.llm.anthropic_llm import AnthropicLLM
from src.providers.llm.openrouter_llm import OpenRouterLLM

logger = logging.getLogger(__name__)

# Single-shot packages are smaller than the retired 3-segment chain, but headroom
# is harmless and writer-owned — raising it never touches the judge or extractor,
# which share the same parse() default (1024).
WRITER_MAX_TOKENS = 8192

SYSTEM_PROMPT = """\
<role>
You are a short-form vertical-video creative director for TikTok, working in the
"is this real?!" lane: caught-on-camera, found-footage clips that look like a
real phone captured something that cannot quite be real. You turn one premise
into a single content package ready to produce and post.
</role>

<inputs>
You receive:
1. A premise — the one idea this video delivers, supplied by the user. Develop
   THIS premise; never substitute your own.
2. A STILL DIALECT block — the image-model prompting rules for the opening frame
   (directive-stack order, camera kit, authentic-imperfection, composition
   traps). Obey it when you write start_keyframe.
3. A MOTION DIALECT block — the prompting grammar for the specific video model
   this clip targets (its preferred structure, light/audio rules, what it drowns
   on). Obey it when you write motion.
4. OPTIONALLY, a set of real TikTok videos that went viral in this lane —
   described by aesthetic descriptors, hook subtype, and a transcript when one
   exists. EVIDENCE of what works, never material to copy. They may be absent;
   when absent, lean on the dialects and the premise alone.
</inputs>

<task>
Produce one complete content package for ONE continuous ~8 second vertical video:
a single uncut take of a believable dramatic micro-event that makes a scrolling
viewer stop and ask "wait — is this real?!". No cuts, no edits, no montage — one
camera, one moment, caught as if by accident. Something small happens and PAYS
OFF inside the eight seconds; the payoff is what earns the replay.

The register is found-footage realism, NOT spectacle. The clip should read as a
real capture of an almost-impossible moment, not as an obviously-generated
"epic" render. The uncanny lands hardest when everything else looks mundane and
true.
</task>

<grounding_rule>
When examples are present, they show you the mechanics that earned views — the
aesthetic, the hook variant, what was said. Transfer the MECHANIC onto the
premise; never reuse a winner's topic, subject, or wording. The topic is always
the supplied premise. When no examples are present, this rule is moot — invent
freely within the lane.
</grounding_rule>

<fields>
Fill every field.

<shot>
ONE shot. It has two prompts you write and one optional third:

start_keyframe — the single opening still, the 3-second scroll-stop frame and the
world's DNA. This is an IMAGE-model prompt: write it in the STILL DIALECT. Lead
with the subject and its identity, then the hard framing/spatial layout, then the
camera kit (lens, light source + direction). Found-footage framing beats polished
composition — a slightly off, handheld, real-phone angle reads truer than a
perfect one. NO palette or grade words (the mood_anchor owns the grade, appended
at render). NO motion words (movement is the motion field). Express scale with
adjectives only (colossal, towering); never measure against a named real object,
or the image model fuses that object into the frame. Vertical 9:16.

motion — the one continuous movement that animates the still over ~8s and lands
the payoff. This is the VIDEO-model i2v prompt: write it in the MOTION DIALECT.
The input still already carries the look, so do NOT restate palette, scene, or
style here — describe only camera move, subject action, timing, and audio. ONE
camera move + ONE subject action; if something moves fast, name the single
element that moves fast, never the whole frame. Build to the payoff with a move
that REVEALS rather than buries it — a pull-back, a tilt-up, a hold that lets the
impossible thing resolve on camera. Do not push in and lose the very thing the
clip is about. End the take deliberately (the moment completes, or holds) — no
hanging action.

  Audio: line — the motion MUST contain an "Audio:" line describing concrete
  diegetic sound, in the MOTION DIALECT's audio form. Name the actual sounds the
  scene would make (footstep on gravel, distant traffic, a sharp wet crack), not
  "ambient sounds". NO music — this is a real capture, not a scored edit.

end_keyframe (optional) — a target final frame, ONLY when the payoff is a
specific visual state the motion must land precisely (a transformation step, a
reveal's end state). Write it as the opening frame moments later with ONLY the
action advanced — same world, same camera, a minimal delta. Most single-shot
clips do NOT need one; leave it null unless the payoff demands a pinned end state.
</shot>

<mood_anchor>
One line: palette, light quality + direction, realism register, and uncanny
register. Appended at render to the still (and end_keyframe if present), so it
must describe only what is TRUE for the whole take. Name a light SOURCE only when
it is lit the entire time (sun, sky, room light) — never a light that ignites
mid-take. Favor authentic-capture cues (natural grain, slight underexposure,
practical light); never quality incantations ("masterpiece", "8K", "cinematic").
</mood_anchor>

<onscreen_text>
Exactly one short, punchy hook line in almost every case — the "is this real?!"
/ "wait what just happened" text that rides over the clip (added manually at
upload). One string in the list. Return an empty list ONLY for a deliberately
textless clip.
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
Leave null unless a person ON CAMERA actually speaks a line as part of the
captured moment (then it is diegetic dialogue, not narration). This lane is not
narrated — do not invent voiceover to fill the field.
</voiceover>

<rationale>
One or two sentences: what makes this premise read as believable-but-impossible,
and how the motion's payoff lands the "is this real?!" beat. For debugging and
eval.
</rationale>

<provenance>
Do not populate model_cli_id, premise, or grounding_hit_ids — the system sets
those itself.
</provenance>
</fields>

<constraints>
  - Develop the supplied premise — never substitute your own concept.
  - ONE continuous take, ~8s, vertical 9:16, photoreal found-footage register.
    No cuts, no montage, no scene jumps.
  - start_keyframe in the still dialect; motion in the motion dialect; obey both
    blocks you were given rather than a generic style.
  - The clip must PAY OFF on camera inside the take — the reveal/event resolves
    visibly. A pretty static frame where nothing happens is the failure.
  - The motion must REVEAL the payoff, not bury it (no push-in that loses the
    concept).
  - motion carries an Audio: line of concrete diegetic sound; no music.
  - Write what is visibly on screen. A word that names a feeling instead of a
    visible thing gives the renderer nothing to draw. Cut empty adjectives (epic,
    amazing, beautiful, stunning); replace each with the concrete subject, light,
    or action it stood for.
</constraints>
"""

def _hydrate_hits(hits: list[RetrievalHit], db: Session) -> list[dict]:
    """
    Build per-hit grounding payloads: transcript from the DB, aesthetic_descriptors
    and hook_subtype from each hit's blueprint_data.

    Only transcripts need a DB round-trip (captions are deliberately not fetched —
    no usable signal). A hit with no transcript row gets transcript=None; absence is
    carried truthfully so _build_envelope decides whether to render a transcript line.
    """

    ids = [h.content_item_id for h in hits]

    stmt = (
        select(RawContentItem.id, Transcript.text)
        .outerjoin(Transcript, RawContentItem.id == Transcript.content_item_id)
        .where(RawContentItem.id.in_(ids))
    )

    rows = db.execute(stmt).all()

    lookup = {id: (text) for id, text in rows}

    out = []
    for hit in hits:
        # A hit whose RawContentItem row no longer exists (stale RAG index
        # entry) degrades to transcript=None — the same handled state as a
        # row with no transcript — instead of a KeyError killing the whole
        # write() call (audit issue 13). Logged so index drift is visible.
        if hit.content_item_id not in lookup:
            logger.warning(
                "RAG hit %s has no RawContentItem row (stale index entry) — "
                "grounding without transcript",
                hit.content_item_id,
            )
        text = lookup.get(hit.content_item_id)
        out.append({
            "transcript": text,
            "aesthetic_descriptors": hit.blueprint_data.get("aesthetic_descriptors", None),
            "hook_subtype": hit.blueprint_data.get("hook_subtype", None),
        })  
    return out
    
def _build_envelope(
    premise: str,
    still_dialect: dict,
    motion_dialect: dict,
    hydrated_hits: list | None,
) -> str:
    """
    Assemble the single-shot user prompt: the premise to develop, the two dialect
    blocks the writer must obey, and (optionally) the retrieved winners.

    The SYSTEM_PROMPT promises the model four labeled inputs, so this emits them as
    labeled sections it can find: the premise (the WHAT), the still dialect (the
    image-model rules for start_keyframe), the motion dialect (the chosen video
    model's grammar for motion), and one block per retrieved winner when grounding
    is supplied. The two dialects are serialized with json.dumps so their full
    rule text — including nested sub-blocks like a model's physics_keywords — lands
    verbatim in the prompt; the model reads them as reference, not as JSON to echo.

    Grounding is optional: when hydrated_hits is None or empty, no Examples section
    is emitted and the writer leans on the dialects and premise alone. Each winner
    block always carries its aesthetic descriptors and hook subtype (the
    always-present signal) and adds a transcript line only when that winner has one.

    Returns:
        The joined prompt string (sections separated by blank lines).
    """

    parts = [
        f"Premise:\n{premise}",
        f"Still dialect:\n{json.dumps(still_dialect, indent=2)}",
        f"Motion dialect:\n{json.dumps(motion_dialect, indent=2)}",
    ]

    if hydrated_hits:
        for i, hit in enumerate(hydrated_hits, 1):
            aesthetic_descriptors = (
                ", ".join(hit["aesthetic_descriptors"])
                if hit["aesthetic_descriptors"]
                else "n/a"
            )
            hook_subtype = hit["hook_subtype"] if hit["hook_subtype"] else "unknown"

            lines = [f"Example {i} — a real video that went viral with these mechanics:"]
            if hit["transcript"] is not None:
                lines.append(f"Transcript: {hit['transcript']}")
            lines.append(f"Aesthetic descriptors: {aesthetic_descriptors}")
            lines.append(f"Hook subtype: {hook_subtype}")

            parts.append("\n".join(lines))

    return "\n\n".join(parts)


class ContentWriter:
    """
    Generates a validated single-shot ContentPackage from a premise via one
    structured-output LLM call.

    Injects still and motion render dialects from RenderRules so prompts target
    the chosen models natively. Optional retrieved hits ground style/lane only.
    """

    def __init__(self, llm: AnthropicLLM | OpenRouterLLM):
        self.llm = llm

    def write(
        self,
        premise: str,
        *,
        rules: RenderRules,
        model_cli_id: str = "veo3_1",
        hits: list[RetrievalHit] | None = None,
        db: Session | None = None,
    ) -> ContentPackage:
        """
        Generate one ContentPackage for a single-shot clip from the given premise.

        Builds a user prompt from the premise, still dialect, motion dialect for
        model_cli_id, and (when hits is not None) hydrated winner examples; runs
        structured output; then code-sets premise, model_cli_id, and
        grounding_hit_ids (never trusted from the LLM).

        Args:
            premise: The one-line idea this video delivers (from PremiseGenerator
                or hand-fed). The writer develops THIS premise, not a substitute.
            rules: Loaded render_rules.yaml — still_dialect and per-model dialect.
            model_cli_id: Motion model the motion prompt targets (default veo3_1).
                Caller/router may override; stamps package.model_cli_id after parse.
            hits: Optional retrieved viral neighbors for style/lane grounding.
                When None, generation is imagination-only.
            db: Required when hits is not None — used to fetch transcripts.

        Returns:
            A validated ContentPackage ready for the thin render adapter.

        Raises:
            TypeError: from SQLAlchemy if hits is provided but db is None.
        """

        if hits is not None:
            if db is None:
                raise ValueError("db is required when hits is provided (transcripts need a DB round-trip)")
            hydrated = _hydrate_hits(hits, db)
        else:
            hydrated = None

        envelope = _build_envelope(
            premise,
            still_dialect=rules.still_dialect(),
            motion_dialect=rules.model(model_cli_id)["dialect"],
            hydrated_hits=hydrated,
        )

        package = self.llm.parse(envelope, ContentPackage, system=SYSTEM_PROMPT, max_tokens=WRITER_MAX_TOKENS)
        package.premise = premise
        package.model_cli_id = model_cli_id
        package.grounding_hit_ids = [h.content_item_id for h in hits] if hits is not None else []

        return package
