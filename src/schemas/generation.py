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

from pydantic import BaseModel, Field


class ContentPackage(BaseModel):
    """
    A single generated TikTok video's full content kit — the writer's output.

    The LLM produces this via structured output, grounded on real viral neighbors
    retrieved by RAG. Every required field must be present for the package to
    validate; optional fields carry None / empty defaults so absence is explicit.

    Attributes:
      video_prompt: Text-to-video prompt describing the visual to generate. Written
        in model-agnostic cinematic grammar for v1 (subject + action + camera +
        style/lighting + motion); tightened to the chosen video model later.
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

    video_prompt: str = Field(
        description="Text-to-video prompt: subject + action + camera + style/lighting + motion."
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
