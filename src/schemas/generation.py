"""
Content generation schemas — the writer's structured output contract.

PIPELINE ROLE:
  BlueprintCandidate (target mechanic combo from the miner) + retrieved viral
  neighbors (P2 RAG)  →  ContentWriter.write()  →  ContentPackage (this file)
  →  chained-continuity render (ONE nano-banana-2 opening still + Kling v3 i2v,
  clip N+1 starting on clip N's extracted last frame) + TikTok post (P3.5).

WHY THIS FILE EXISTS:
  ContentPackage is the schema the LLM fills via structured output (the Blueprint
  extractor run backwards). It defines what a valid, generated content kit looks
  like — one TikTok video's full package: the chained shot segments, on-screen
  overlays, caption, hashtags, optional voiceover, plus provenance (which retrieved
  winners grounded the generation). Pydantic validation is the guard rail: a
  generated package that omits a required field is rejected, not silently shipped.

PARADIGM (chained-continuity v3, design 2026-06-10):
  One video = ONE continuous ~15s experience assembled from 3 chained ~5s clips.
  No hard cuts: the camera/world flows the full duration. Still-first survives with
  a role change — ONE opening still (segment 1's start_keyframe, the photoreal hook
  frame that sells the impossible subject); segments 2-3 inherit their start frame
  mechanically from the previous clip's extracted last frame, so the world is never
  re-rolled. The old vignette doctrine's ban on cause→effect across cuts is INVERTED:
  development is now mandatory (one developing micro-narrative). The named failure is
  the static "ant corpse" take — structurally clean, but nothing develops.

  The writer's output is render-agnostic TEXT: keyframes are described, never image
  paths. The chain mechanism (last-frame extract + concat) lives in the downstream
  render layer, NOT in this schema — so a future one-shot model swaps the render
  adapter without touching the writer.

  Replaces the retired vignette schema (organizing_principle, three independent
  stills, "no event spans a cut"), falsified by the 2026-06-10 render taste test.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


Device = Literal[
    "embodiment",
    "transformation",
    "scale_traversal",
    "encounter",
    "reveal",
    "wrongness_creep",
    "time_compression",
]


class Shot(BaseModel):
    """
    One ~5s segment of the chained-continuity video — a single i2v clip.

    A ContentPackage holds exactly three Shots in chain order. They are NOT
    independent vignettes: the world flows continuously across them because the
    render layer starts each clip on the previous clip's extracted last frame.
    Each Shot describes that segment's motion (and, when the segment must reach a
    specific visual state, its end_keyframe) as TEXT — never an image path.

    The opening still is generated ONCE, from segment 1's start_keyframe, and its
    realism is inherited forward. Two segment roles:

      - SEGMENT 1 (the opener) — carries start_keyframe: the only generated still,
        the 3-second scroll-stop hook, the strongest frame of the video. Animated
        with the small or developing move in `motion`. May also carry an end_keyframe
        if segment 1 itself reaches a specific state.
      - SEGMENTS 2-3 (inheritors) — start_keyframe is None; their start frame is
        the previous clip's extracted last frame, supplied mechanically by the
        render layer, not written by the writer. Animated with `motion`, plus an
        optional end_keyframe when the segment must hit a specific visual target
        (a transformation step, a time-compression state, an interaction completing).

    end_keyframe is used (any segment, most commonly 2/3) when the segment must reach
    a specific visual state. Written as "the inherited frame, moments later, with ONLY
    the action advanced" — the minimal-delta rule, so the pair reads as the same world
    a moment apart, not two mismatched shots that morph. The render layer feeds
    start+end to Kling's start/end mode to interpolate the A→B action.

    Seam-momentum rule (§4): each segment's motion should END with the action that
    OPENS the next segment's motion, so the chain seams carry momentum instead of
    stalling — a single still frame carries position but not velocity, so a motion
    that dies at the seam reads as a cut on fast action.

    The package-level mood_anchor (NOT a Shot field) is appended verbatim at render to
    the opening still and to every end_keyframe, locking the grade of every generated
    frame so the continuous take reads as one piece.

    Attributes:
      start_keyframe: Segment 1 ONLY — the photoreal FROZEN frame that opens the
        video: camera framing + subject + action frozen at an instant + lighting
        source/direction. Generates the one opening still. Carries NO palette
        (mood_anchor owns the grade). Must be a frozen peak, NOT motion ("tentacle
        erupting" smears the still); movement belongs only in `motion`. None for
        segments 2-3, which inherit their start frame from the previous clip.
      end_keyframe: Optional, any segment — the inherited (or opening) frame a moment
        later with ONLY the action advanced, used when the segment must reach a
        specific visual state. None marks a segment with no specific end-state to
        reach. Changing more than the action here (different camera/subject) makes the
        start+end pair morph.
      motion: The ONE movement that animates this segment over ~5s, no style words.
        For a keyframed segment: the A→B action the start+end i2v interpolates. For an
        idle segment: the continuous/ambient move. Should end on the action that opens
        the next segment's motion (seam-momentum rule).
    """

    start_keyframe: str | None = Field(
        default=None,
        description="Segment 1 ONLY: photoreal FROZEN opening frame (camera + subject + frozen action + lighting; no palette). None for inherited segments 2-3.",
    )
    end_keyframe: str | None = Field(
        default=None,
        description="Optional: inherited frame moments later, ONLY the action advanced. None = no specific end-state to reach.",
    )
    motion: str = Field(
        description="The one ~5s movement animating this segment; no style words. Ends on the next segment's opening action (seam momentum)."
    )


class ContentPackage(BaseModel):
    """
    A single generated TikTok video's full content kit — the writer's output.

    The LLM produces this via structured output, grounded on real viral neighbors
    retrieved by RAG. Every required field must be present for the package to
    validate; optional fields carry None / empty defaults so absence is explicit.

    The video is ONE continuous chained-continuity take (see module docstring), not a
    montage. The three shots are sequential chained segments; the package-level
    mood_anchor and device carry what used to be smeared across per-shot fields.

    Attributes:
      shots: The 3 chained segments, in chain order (opening → middle → closing).
        Exactly three — enforced at the schema level, not left to the prompt. The
        first segment carries the only start_keyframe (the generated opening still);
        segments 2-3 inherit their start frame from the previous clip's last frame.
      device: The single creative device (closed 7-menu) that answers "what makes
        THIS continuous 15s gripping?", routed from the premise. Replaces the retired
        organizing_principle. One per package; the anti-monotony guard made a typed,
        evalable field rather than a hidden writer habit, watched across runs by the
        device_distribution metric.
      device_rationale: One or two sentences justifying the device pick from THIS
        premise — surfaces the choice so cross-premise monotony is detectable.
        Replaces principle_rationale.
      mood_anchor: Palette + lighting + realism level + uncanny register for the whole
        video. Package-level (one grade for the continuous take, not per-shot):
        appended VERBATIM at render to the opening still and every end_keyframe, so all
        generated frames land in one grade and the take reads as one piece.
      onscreen_text: Text overlays rendered on the video, in display order. Required —
        the writer must consciously address overlays (pass an empty list only if the
        video genuinely has none).
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
        description="The 3 chained segments in chain order (opening, middle, closing); exactly three.",
    )
    device: Device = Field(
        description="The chosen creative device the continuous take is built on. One of a closed 7-menu; routed from the premise."
    )
    device_rationale: str = Field(
        description="Why this device fits THIS premise. One or two sentences."
    )
    mood_anchor: str = Field(
        description="Palette + lighting + realism + uncanny register for the whole video; appended verbatim to the opening still and every end_keyframe."
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

    @model_validator(mode="after")
    def _check_chain_contract(self) -> "ContentPackage":
        """
        Enforce the chain contract that the field types alone cannot express.

        Two invariants from design §4 (the chain structure, not just well-typed shots):

          1. Segment 1 MUST carry a start_keyframe — it is the only generated still,
             the photoreal hook that seeds the chain. A package whose opener has no
             start frame has nothing to render the world from.
          2. Segments 2-3 MUST NOT carry a start_keyframe — their start frame is
             inherited mechanically from the previous clip's extracted last frame. A
             written start_keyframe there means the writer tried to re-roll the world
             mid-chain, which breaks continuity.

        Raises:
          ValueError: if the opener lacks a start_keyframe, or any inheriting segment
            supplies one. Pydantic surfaces this as a ValidationError at construction.
        """
        opener, *inheritors = self.shots
        if opener.start_keyframe is None:
            raise ValueError(
                "Segment 1 must carry a start_keyframe (the opening still seeds the chain)."
            )
        for offset, shot in enumerate(inheritors, start=2):
            if shot.start_keyframe is not None:
                raise ValueError(
                    f"Segment {offset} must not carry a start_keyframe "
                    "(it inherits its start frame from the previous clip's last frame)."
                )
        return self
