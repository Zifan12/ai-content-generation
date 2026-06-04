"""
Content generation schemas — the writer's structured output contract.

PIPELINE ROLE:
  BlueprintCandidate (target mechanic combo from the miner) + retrieved viral
  neighbors (P2 RAG)  →  ContentWriter.write()  →  ContentPackage (this file)
  →  text-to-video provider + TikTok post (P3.5).

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


class Shot(BaseModel):
    """
    One beat of the 3-shot montage — a single ~5s text-to-video clip.

    A ContentPackage holds exactly three Shots in arc order (setup → turn →
    payoff). Each Shot carries its own cinematic prompt (the renderer feeds this
    to the T2V model to produce one clip) plus a mood_anchor that the writer
    repeats VERBATIM across all three shots so the montage reads as one piece
    even when the scenes differ. arc_role names which beat this shot is.

    Attributes:
      cinematic_prompt: Model-agnostic T2V prompt for THIS shot only — subject +
        action + camera + lighting/palette + motion, scoped to one ~5s beat (not
        the whole video). Same cinematic grammar as the retired single
        video_prompt, but one beat's worth.
      mood_anchor: Palette + lighting + realism level + uncanny register. MUST be
        described identically across all three shots — this is the connective
        tissue that holds a montage of differing scenes together. Not a fixed
        subject or location; scenes may differ, mood may not.
      arc_role: Which structural beat this shot is. Constrained to the three
        montage roles so the writer cannot drift into ad-hoc labels: "setup"
        (hook + the what-if framing), "turn" (the impossible thing happens /
        escalates), "payoff" (the consequence / reveal that lands the premise).
    """

    cinematic_prompt: str = Field(
        description="T2V prompt for THIS shot: subject + action + camera + lighting/palette + motion."
    )
    mood_anchor: str = Field(
        description="Palette + lighting + realism + uncanny register; MUST be identical across all 3 shots."
    )
    arc_role: Literal["setup", "turn", "payoff"] = Field(
        description="Which beat this shot is: setup (hook/what-if), turn (escalation), payoff (reveal)."
    )


class ContentPackage(BaseModel):
    """
    A single generated TikTok video's full content kit — the writer's output.

    The LLM produces this via structured output, grounded on real viral neighbors
    retrieved by RAG. Every required field must be present for the package to
    validate; optional fields carry None / empty defaults so absence is explicit.

    Attributes:
      shots: The 3-shot montage, in arc order (setup → turn → payoff). Exactly
        three — enforced at the schema level, not left to the prompt. Replaces the
        retired single video_prompt: one static shot rendered bland video, so the
        writer is now forced to develop the premise across three connected beats.
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
        description="The 3-shot montage in arc order (setup, turn, payoff); exactly three.",
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
