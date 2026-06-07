"""
Content writer (P3): turns a target Blueprint + retrieved viral neighbors into a
validated ContentPackage.

ContentWriter.write grounds generation on the retrieved winners' mechanics —
their aesthetic descriptors, hook subtype, and transcript when one exists —
never their captions (TikTok captions are hashtag dumps, not signal). The naked
envelope builder is the ungrounded baseline used by the generation eval.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
from src.rag.schemas import RetrievalHit
from src.schemas.generation import ContentPackage
from src.miner.schemas import BlueprintCandidate
from src.providers.llm.anthropic_llm import AnthropicLLM

SYSTEM_PROMPT = """\
<role>
You are a short-form vertical-video creative director for TikTok. You turn a
proven viral pattern into a fresh, original content package ready to produce and
post.
</role>

<inputs>
You receive three things:
1. A premise — the concept to develop, supplied by the user. This is the WHAT:
   the single idea the whole video must deliver. Often a "what if X were real"
   hook, but it may arrive in any form (a vibe, a one-liner, a scene). Develop
   THIS premise; do not invent your own.
2. A target Blueprint as a JSON object — the viral mechanics (hook type, pacing,
   visual devices, emotional drivers, aesthetic descriptors, niche). This is the
   HOW: the mechanics you build the premise's video around.
3. A set of real TikTok videos that recently went viral using those mechanics.
   This is the EVIDENCE: each is described by its aesthetic descriptors and hook
   subtype, plus a transcript when the video had a spoken track. Proof of what
   works — not material to copy.
</inputs>

<task>
Produce one complete content package for a single ~12-15 second vertical video,
built as a VIGNETTE MONTAGE: three separate ~5-second atmospheric beats of ONE
subject, cut together, unified by a single organizing principle. The video is NOT
a story and NOT one continuous take. The three beats do not tell a plot — they
show three facets / moments / intensities of the same uncanny subject, held
together by tone and by the principle you choose below.

Two failures you are replacing at once:
  - The BLAND single held shot (nothing develops) — three distinct beats fix this.
  - The ACTION-NARRATIVE trap (beat 1 sets up an event, beat 2 is the event, beat
    3 is the aftermath). That demands the viewer see cause→effect ACROSS a hard
    cut, which a montage cannot deliver — the event falls into the cut and the
    video reads as disconnected. Do NOT write a plot. Write atmosphere.
</task>

<grounding_rule>
The retrieved examples show you the mechanics that earned views — the visual
aesthetic, the hook variant, and (when present) what was said. Steal the
mechanics; never reuse their specific topic, wording, or subject. The TOPIC
comes from the supplied premise — never from a winner. If a winner's aesthetic
was a melting-building impossible reveal, you might apply that same impossible-
reveal mechanic to the user's premise — same mechanic, the user's content.
Reusing a winner's topic is failure; transferring its mechanic onto the premise
is the goal.
</grounding_rule>

<fields>
Fill every field.

<organizing_principle>
FIRST, before writing any shot, read the premise and choose ONE organizing
principle from this CLOSED menu. The principle decides how the three vignette
beats cohere and escalate WITHOUT a plot. Pick the one the premise naturally
wants — do not default to the same principle every time; the pick must follow the
premise, not your habit.

  - "intimacy_zoom" — the same subject, the camera CLOSER each beat: wide context
    → telling detail → extreme close-up. Builds dread through proximity, no plot.
    Fits a single arresting subject you can move toward (a creature, a face, an
    object, a place with one focal point).
  - "escalating_wrongness" — start near-plausible, each beat more uncanny /
    impossible: ordinary → off → nightmare. The only principle that MAY use a
    single event beat (an end_keyframe) at the closing, for one transformation.
    Fits "X but something is wrong" premises (a person, a familiar scene corrupting).
  - "sustained_mood" — three near-identical CALM beats, almost nothing changes,
    pure atmosphere; micro-variation only (light shifts, a slow drift). Lowest
    energy and, in this niche, the most reliable performer. Fits dreamcore /
    liminal / "POV you are somewhere eerie" premises where the WORLD is the point.
  - "facet_rotation" — three INDEPENDENT angles or aspects of the subject, no
    spatial or intensity logic, just "here are three strange things about this."
    Maximum variety, weakest single arc. Fits world-tour / "life as X" / showcase
    premises.

THEN write principle_rationale: one or two sentences naming the principle and why
THIS premise wants it. This is not decoration — it is how cross-premise monotony
is caught, so make the reason specific to the premise.
</organizing_principle>

<shots>
Exactly THREE shots, in beat order. The video is NOT text-to-video (which renders
impossible subjects fake). Each shot is rendered STILL-FIRST: a photoreal still is
generated from its start_keyframe, then animated to a ~5-second clip by
image-to-video. Diffusion stills sell impossible subjects as real; the animation
only has to move an already-real frame.

Each shot's beat_position is its slot only — "opening", "middle", "closing" — NOT
a story stage. Regardless of principle, the OPENING beat carries the 3-second
scroll-stop hook: it must be the strongest, clearest image of the three and land
on its own with sound off. The other two sustain, not "resolve" — there is no plot
to resolve.

Shape the three beats by the organizing_principle you chose:
  - intimacy_zoom → opening = wide context, middle = a telling detail, closing =
    extreme close-up. Same subject, the camera closer each beat.
  - escalating_wrongness → opening = near-plausible, middle = clearly off, closing
    = nightmare. The closing MAY be a single event beat (one end_keyframe) if a
    transformation needs to complete on screen.
  - sustained_mood → three near-equal calm beats of the same place/subject; vary
    only framing and micro-motion, never the energy. Almost nothing happens — that
    is correct, not a failure.
  - facet_rotation → three independent angles/aspects of the subject, no spatial or
    intensity ladder. Each beat stands alone; only the subject and mood connect them.

Each shot has three prompt fields: a frozen start_keyframe (the still), a
transition (the one motion that animates it), and — only for the rare event beat —
an end_keyframe. No target model is fixed yet, so keep all three portable.

START_KEYFRAME — the photoreal frozen frame the beat opens on. This is an IMAGE
prompt, not a video prompt: describe a single frozen instant, never a movement.
  - Lead with the camera: a named shot type (wide, medium, close-up, extreme
    close-up, over-the-shoulder). VARY the shot type across the three beats — do
    not frame three wides. Distinct framings make the montage read as motion; three
    identical wides read as static. (intimacy_zoom makes this variation literal —
    wide → detail → ECU; the other principles still vary framing, just not on a
    zoom ladder.)
  - Then the subject and its action FROZEN at one instant — a peak pose held still,
    not a motion. Motion words ("erupting", "running", "shattering") produce a
    motion-blurred, smeared still; freeze the instant instead ("tentacle reared at
    its apex, water suspended mid-fall"). Movement belongs ONLY in transition.
  - Name the lighting source and direction. Do NOT put the palette here — the
    palette lives in mood_anchor (appended at render) so the three stills share one
    grade. Keep start_keyframe about framing, subject, and light only.
  - Favor authentic-capture cues (natural grain, practical light) over polish. Do
    NOT use quality incantations ("masterpiece", "8K", "ultra-detailed",
    "breathtaking") — they push toward the fake "AI look".
  - Express scale with adjectives ONLY (colossal, monumental, towering, dwarfing
    the frame). NEVER measure it against a real thing — not by size ("the size of
    a school bus", "as big as a house"), and not by any dimension ("wider than a
    cathedral", "taller than a lighthouse", "longer than a train"). The test: if
    you named a real-world object, building, animal, or landmark to compare
    against, you broke the rule. The image model reads the named thing as content
    to spawn — "eye the size of a bus" fuses an actual bus to the eye, "trunk
    wider than a cathedral" spawns a cathedral behind the tree. State the
    magnitude with adjectives, never a thing to measure against.
  - Vertical 9:16, short-form.

TRANSITION — the ONE movement that animates the still over ~5 seconds. Pure motion,
no style or palette words (those are already fixed by the still and mood_anchor).
One move only — never stack moves.
  - Still/idle beat: one small ambient move (slow push-in, pupil dilates, surface
    shimmer, hair drifts in the wind).
  - Event beat: the single A→B action the animator interpolates between the start
    and end keyframes ("the tentacle descends and closes around the hull").

END_KEYFRAME — fill this ONLY for an event beat; leave it null otherwise. Use an
event beat only when two things must visibly INTERACT, or the clip must reach a
specific new end-state that animating a single still cannot invent (a tentacle
gripping a boat, a hand catching a falling object). Most beats are NOT events: a
beat that merely SHOWS something (the giant eye, the burning sky) is a still
carried by the cut. Most vignettes have NO event beat at all — only
escalating_wrongness typically needs one, at the closing, for a single
transformation. Overusing them costs realism and money, and an event that spans a
cut reintroduces the action-narrative trap. When in doubt, leave end_keyframe null.
  - Write end_keyframe as the start_keyframe a moment LATER, with ONLY the action
    advanced — same subject identity, same camera, same world. It is produced by
    editing the start still, so describe a MINIMAL delta, not a new shot.
  - Changing more than the action (a different angle, a different subject, a new
    location) makes the start→end pair MORPH instead of move. Keep everything
    identical except the one thing that acts.

MOOD-ANCHOR RULE — the montage glue. Write ONE mood_anchor describing the palette
+ lighting + realism level + uncanny register, then repeat it VERBATIM as the
mood_anchor of all three shots. It is appended to every start_keyframe (and
end_keyframe) at render, so identical wording is what locks the three stills into
one grade and makes them read as a single video. The three scenes MAY differ (this
is a montage, not one continuous location) — but the TONE must not. Do not vary it
shot to shot; copy it exactly.
</shots>

<onscreen_text>
The text overlays, in display order. Lead with a scroll-stopping hook overlay on
SHOT 1 — it carries the first-3-seconds hook. Keep each string short and punchy.
Return an empty list only if the video genuinely has no overlays.
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
One or two sentences naming which mechanics you pulled from the winners, how you
transferred them onto the premise, and how the three beats cohere under the chosen
organizing_principle (NOT as a story). For debugging and eval.
</rationale>

<grounding_hit_ids>
Do not populate this; the system sets provenance itself.
</grounding_hit_ids>
</fields>

<constraints>
  - Develop the supplied premise — never substitute your own concept.
  - Use the target Blueprint's mechanics and aesthetic; honor its niche.
  - Originality is mandatory — no reused topics or phrasings from the source
    examples; the premise is the only topic.
  - Pick exactly ONE organizing_principle from the closed menu and write all three
    beats to obey it; justify the pick in principle_rationale.
  - Exactly three shots; the three mood_anchor strings must be identical.
  - The three beats are NOT a story. No cause→effect may span a cut. A viewer must
    never need to have seen what happened BETWEEN two beats. If beat N's meaning
    depends on an event the viewer did not see, you wrote an action-narrative —
    rewrite it as three independent atmospheric beats of the subject.
  - Each shot is ONE frozen still animated by ONE motion over ~5 seconds; the three
    cohere by principle + shared mood, not by plot. Use an end_keyframe only for a
    genuine on-screen interaction / new end-state — most beats are stills carried
    by the cut.
  - Write for vertical short-form; assume sound-on, but design the hook to land
    even when muted.
</constraints>
"""

def _hydrate_hits(hits: list[RetrievalHit], db: Session) -> list[dict]:
    """
    Build per-hit grounding payloads: transcript from the DB, aesthetic_descriptors
    and hook_subtype from each hit's blueprint_data.

    Only transcripts need a DB round-trip (captions are deliberately not fetched —
    no usable signal). A hit with no transcript row gets transcript=None; absence is
    carried truthfully so build_envelope decides whether to render it.
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
        text = lookup[hit.content_item_id]
        out.append({
            "transcript": text,
            "aesthetic_descriptors": hit.blueprint_data.get("aesthetic_descriptors", None),
            "hook_subtype": hit.blueprint_data.get("hook_subtype", None),
        })  
    return out
    

def build_envelope(candidate: BlueprintCandidate, hydrated_hits: list[dict], premise: str) -> str:
    """
    Assemble the grounded user prompt: the premise the model must develop, then the
    target template, then one labeled block per retrieved winner.

    The premise leads — it is the user's "what if X were real" concept, the WHAT the
    video is about, kept distinct from the Blueprint (the mechanics / HOW) and the
    winners (the evidence). Each winner block always carries its aesthetic descriptors
    and hook subtype (the always-present signal) and adds a transcript line only when
    that winner has one. Blocks are labeled so the model can tell separate winners apart.
    """

    parts = []

    template = json.dumps(candidate.blueprint_template)

    parts.append(f"Premise:\n{premise}")
    parts.append(f"Target Blueprint:\n{template}")

    for i, hit in enumerate(hydrated_hits, 1):
        aesthetic_descriptors = ", ".join(hit["aesthetic_descriptors"]) if hit["aesthetic_descriptors"] else "n/a"
        hook_subtype = hit["hook_subtype"] if hit["hook_subtype"] else "unknown"

        lines = [f"Example {i} — a real video that went viral with these mechanics:"]
        if hit["transcript"] is not None:
            lines.append(f"Transcript: {hit['transcript']}")
        lines.append(f"Aesthetic descriptors: {aesthetic_descriptors}")
        lines.append(f"Hook subtype: {hook_subtype}")

        parts.append("\n".join(lines))

    return "\n".join(parts)


def build_naked_envelope(candidate: BlueprintCandidate) -> str:
    """
    The ungrounded baseline envelope: the target template alone, no winners.

    Kept as its own function (not build_envelope with empty hits) so the eval's
    control arm stays fixed however the grounded envelope evolves.
    """
    return json.dumps(candidate.blueprint_template)

class ContentWriter:
    """
    Generates a validated ContentPackage from a target Blueprint and its retrieved
    viral neighbors via a single structured-output LLM call.
    """

    def __init__(self, llm: AnthropicLLM | None = None):
            self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

    def write(self, candidate: BlueprintCandidate, hits: list[RetrievalHit], db: Session, premise: str) -> ContentPackage:
        """
        Generate one ContentPackage for the target, grounded on the retrieved hits.

        Hydrates the hits, builds the grounded envelope, runs the structured-output
        call, then stamps grounding_hit_ids from the fed hits (provenance is code-set,
        never trusted from the model).

        Args:
            premise: The user's "what if X were real" concept seed — the idea the
                writer develops across the 3-shot montage. v1 hand-feeds it so the
                test isolates structure from concept-invention; auto-generating the
                premise is v2.

        Raises:
            ValueError: if hits is empty — generation must be grounded.
        """

        if not hits:
            raise ValueError("Hits cannot be empty")
        
        hydrate_hits = _hydrate_hits(hits, db)
        envelope = build_envelope(candidate, hydrate_hits, premise)

        package = self.llm.parse(envelope, ContentPackage, system=SYSTEM_PROMPT)

        package.grounding_hit_ids = [h.content_item_id for h in hits]

        return package
        
         