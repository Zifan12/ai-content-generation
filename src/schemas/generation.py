"""
Content generation schemas — the writer's structured output contract.

PIPELINE ROLE:
  BlueprintCandidate (target mechanic combo from the miner) + retrieved viral
  neighbors (P2 RAG)  →  ContentWriter.write()  →  ContentPackage (this file)
  →  still-first image+i2v render (nano-banana-2 stills + Kling v3 pro keyframe
  i2v) + TikTok post (P3.5).

WHY THIS FILE EXISTS:
  ContentPackage is the schema the LLM fills via structured output (the Blueprint
  extractor run backwards). It defines what a valid, generated content kit looks
  like — one TikTok video's full package: the visual prompt, on-screen overlays,
  caption, hashtags, optional voiceover, plus provenance (which retrieved winners
  grounded the generation). Pydantic validation is the guard rail: a generated
  package that omits a required field is rejected, not silently shipped.

  Replaces the retired ScriptPackage/ScriptRequest (talking-head hook/body/cta),
  which were wrong after the surreal_hyperreal visual-first pivot.
"""

from typing import Literal

from pydantic import BaseModel, Field


OrganizingPrinciple = Literal[
    "intimacy_zoom",
    "escalating_wrongness",
    "sustained_mood",
    "facet_rotation",
]


class Shot(BaseModel):
    """
    One beat of the 3-shot montage — a still-first, keyframe-driven i2v clip.

    A ContentPackage holds exactly three Shots in beat order (opening → middle →
    closing) — three atmospheric vignettes of one subject unified by an
    organizing_principle, NOT a causal story (no event spans a cut). Each Shot is
    rendered NOT as text-to-video (which renders impossible subjects fake) but
    still-first: the renderer generates a photoreal STILL from start_keyframe
    (+ mood_anchor appended), then animates it via image-to-video. Two beat kinds,
    distinguished by end_keyframe:

      - STILL / IDLE beat (end_keyframe is None) — one keyframe, animated with the
        small ambient move in `transition` (push-in, blink, shimmer) or held and
        carried by the cut. Single-image i2v keeps it photoreal but can only idle.
      - EVENT beat (end_keyframe set) — two things must visibly interact / a new
        state must be reached (a tentacle grips a hull). Single-image i2v cannot
        invent that, so the renderer feeds start_keyframe + end_keyframe to a
        start+end i2v model (Kling v3 pro) which interpolates the A→B action in
        `transition`. The end frame is produced by image-EDITing the start still
        (change ONLY the action), so the pair reads as the same world a moment
        apart instead of two mismatched shots that morph.

    mood_anchor is the writer's continuity lever: appended VERBATIM to every
    keyframe so all three stills land in one grade. beat_position names the slot.

    Attributes:
      start_keyframe: The photoreal FROZEN FRAME that opens this beat — camera
        framing + subject + action frozen at an instant + lighting source/direction.
        Generates the still. Carries NO palette (mood_anchor owns the grade).
        Must be a frozen peak, NOT motion ("tentacle erupting" smears the still);
        movement belongs only in `transition`.
      end_keyframe: Event beats ONLY — the SAME world a moment later with only the
        action advanced (produced by image-editing the start still). None marks a
        still/idle beat with no specific end-state to reach. Changing more than the
        action here (different camera/subject) makes the start+end pair morph.
      transition: The ONE movement that animates this beat over ~5s, no style words.
        For an event beat: the A→B action the start+end i2v interpolates. For a
        still/idle beat: the ambient move (or empty if the beat is a held cut).
      mood_anchor: Palette + lighting + realism level + uncanny register. MUST be
        described identically across all three shots and appended to each keyframe
        at still generation — this is what locks the grade across the stills so a
        montage of differing scenes reads as one piece. Scenes may differ, mood may
        not.
      beat_position: Which slot this shot fills in the montage. Position only, NOT
        a story stage: "opening" (carries the 3-second scroll-stop hook — the
        strongest image), "middle", "closing". The cohesion + escalation across the
        three comes from the package's organizing_principle, not from a causal arc.
    """

    start_keyframe: str = Field(
        description="Photoreal FROZEN frame opening this beat: camera + subject + frozen action + lighting. No palette."
    )
    end_keyframe: str | None = Field(
        default=None,
        description="Event beats only: same world a moment later, ONLY the action advanced. None = still/idle beat.",
    )
    transition: str = Field(
        description="The one ~5s movement animating this beat (A→B for events, ambient for stills); no style words."
    )
    mood_anchor: str = Field(
        description="Palette + lighting + realism + uncanny register; identical across all 3 shots, appended to every keyframe."
    )
    beat_position: Literal["opening", "middle", "closing"] = Field(
        description="Position in the montage: opening (carries the 3-sec hook), middle, closing. Position only — NOT a story stage."
    )


class ContentPackage(BaseModel):
    """
    A single generated TikTok video's full content kit — the writer's output.

    The LLM produces this via structured output, grounded on real viral neighbors
    retrieved by RAG. Every required field must be present for the package to
    validate; optional fields carry None / empty defaults so absence is explicit.

    Attributes:
      shots: The 3-shot vignette montage, in beat order (opening → middle →
        closing). Exactly three — enforced at the schema level, not left to the
        prompt. Replaces the retired single video_prompt: one static shot rendered
        bland video, so the writer now spreads the premise across three connected
        beats unified by organizing_principle (not a causal story).
      organizing_principle: The closed-menu vignette cohesion principle the 3 beats
        obey (intimacy_zoom / escalating_wrongness / sustained_mood /
        facet_rotation). Picked from the premise; the anti-monotony guard made a
        typed, evalable field rather than a hidden writer habit.
      principle_rationale: One or two sentences justifying the principle pick from
        THIS premise — surfaces the choice so cross-premise monotony is detectable.
      onscreen_text: Text overlays rendered on the video, in display order. Required
        — the writer must consciously address overlays (pass an empty list only if
        the video genuinely has none).
      caption: The TikTok caption posted with the video.
      hashtags: Discovery tags for the post.
      voiceover: Narration script, or None when the video has no spoken track.
        None (distinct from empty string) means "no narration" by design.
      grounding_hit_ids: content_item_ids of the retrieved winners that grounded
        this generation. CODE-SET from the fed hits, never trusted from the LLM —
        provenance for the closed loop, not a field the model is asked to echo.
      rationale: Optional free-text explanation of the creative choices the LLM made
        (useful for debugging / eval), or None.
    """

    shots: list[Shot] = Field(
        min_length=3,
        max_length=3,
        description="The 3-shot vignette montage in beat order (opening, middle, closing); exactly three.",
    )
    organizing_principle: OrganizingPrinciple = Field(
        description="The chosen vignette cohesion principle the 3 beats obey. One of a closed menu; picked from the premise."
    )
    principle_rationale: str = Field(
        description="Why this principle fits THIS premise. One or two sentences."
    )
    onscreen_text: list[str] = Field(
        description="On-screen text overlays in display order; empty list only if the video has none."
    )
    caption: str = Field(description="TikTok caption posted with the video.")
    hashtags: list[str] = Field(description="Discovery hashtags for the post.")
    voiceover: str | None = Field(
        default=None,
        description="Narration script, or null if the video has no spoken track.",
    )
    grounding_hit_ids: list[int] = Field(
        default_factory=list,
        description="content_item_ids of the grounding winners; code-set, not LLM-generated.",
    )
    rationale: str | None = Field(
        default=None,
        description="Optional explanation of the creative choices made.",
    )
