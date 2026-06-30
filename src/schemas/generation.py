"""
Content generation schemas — the writer's structured output contract.

PIPELINE ROLE:
  Premise (imagination) + optional RAG hits  →  ContentWriter.write()
  →  ContentPackage (this file)  →  single-shot render (nano-banana-2 opening still
  + Veo 3.1 i2v, one continuous ~8s clip) + TikTok post (P3.5).

WHY THIS FILE EXISTS:
  ContentPackage is the schema the LLM fills via structured output. It defines what
  a valid, generated content kit looks like — one TikTok video's full package: the
  single shot (still + motion prompts), on-screen hook text, caption, hashtags,
  optional voiceover, plus provenance (premise, motion model, grounding hits).
  Pydantic validation is the guard rail: a generated package that omits a required
  field is rejected, not silently shipped.

PARADIGM (single-shot believable micro-narrative, design 2026-06-22):
  One video = ONE continuous ~8s take, vertical 9:16, photoreal surreal_hyperreal.
  Believable dramatic micro-event ("is this real?!") — not a montage, not a 3-clip
  chain. ONE opening still (shot.start_keyframe) seeds ONE i2v motion pass
  (shot.motion, including a diegetic Audio: line). No last-frame handoff, no cuts,
  no stitch.

  The writer's output is render-agnostic TEXT: keyframes are described, never image
  paths. mood_anchor (package-level) is appended verbatim at render to the opening
  still only, locking the grade. onscreen_text is the hook line for manual overlay
  at upload — the pipeline does not burn it into the clip.

  Replaces the retired chained-continuity schema (3 shots, Device enum,
  last-frame extract + concat), falsified by the single-shot pivot.
"""

from pydantic import BaseModel, ConfigDict, Field


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """
    The only visual segment in a single-shot clip — one still → one i2v take (~8s).

    Describes the opening frozen frame and the continuous motion through payoff as
    TEXT — never an image path. mood_anchor lives on ContentPackage, not here; it
    is appended at render to the opening still only.

    Attributes:
      start_keyframe: Subject-first frozen opening frame — camera framing, subject,
        action frozen at an instant, lighting source/direction. Generates the one
        opening still. Carries NO palette (mood_anchor owns the grade). Must be a
        frozen peak, NOT motion; movement belongs only in `motion`.
      motion: The continuous move through payoff over ~8s, no style words. Includes
        a diegetic `Audio:` line (concrete sound, no music by default).
      end_keyframe: Rarely used optional target state. Most clips omit this.
    """

    start_keyframe: str
    motion: str
    end_keyframe: str | None = None


class ContentPackage(BaseModel):
    """
    A single generated TikTok video's full content kit — the writer's output.

    The LLM produces this via structured output. Every required field must be
    present for the package to validate; optional fields carry None / empty defaults
    so absence is explicit.

    The video is ONE continuous single-shot take (see module docstring), not a montage.

    Attributes:
      shot: Exactly one Shot — the only visual segment.
      model_cli_id: Motion model the prompts target (e.g. "veo3_1"). Code-set by the
        writer caller, not trusted from the LLM.
      premise: Source one-line premise. Code-set provenance, not trusted from the LLM.
      mood_anchor: Palette + lighting + realism + uncanny register for the clip;
        appended VERBATIM at render to the opening still.
      onscreen_text: Hook line(s) for manual TikTok overlay at upload; usually
        exactly one. Empty list only for a deliberately textless clip.
      caption: The TikTok caption posted with the video.
      hashtags: Discovery tags for the post.
      voiceover: Rare diegetic dialogue (→ model Dialogue: line), not narration.
        None means no spoken line by design.
      grounding_hit_ids: content_item_ids of retrieved winners that grounded this
        generation. CODE-SET from fed hits, never trusted from the LLM.
      rationale: Optional free-text explanation of creative choices, or None.
    """

    model_config = ConfigDict(extra="forbid")

    shot: Shot
    model_cli_id: str = Field(
        description="Motion model CLI id the prompts target (e.g. veo3_1)."
    )
    premise: str = Field(description="Source one-line premise; code-set provenance.")
    mood_anchor: str = Field(
        description="Palette + lighting + realism + uncanny register; appended to opening still."
    )
    onscreen_text: list[str] = Field(
        description="Hook line(s) for manual overlay at upload; empty only if textless."
    )
    caption: str = Field(description="TikTok caption posted with the video.")
    hashtags: list[str] = Field(description="Discovery hashtags for the post.")
    voiceover: str | None = Field(
        default=None,
        description="Rare diegetic dialogue, or null if no spoken line.",
    )
    grounding_hit_ids: list[int] = Field(
        default_factory=list,
        description="content_item_ids of grounding winners; code-set, not LLM-generated.",
    )
    rationale: str | None = Field(
        default=None,
        description="Optional explanation of the creative choices made.",
    )
