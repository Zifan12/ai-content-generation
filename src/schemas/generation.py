"""
Content generation schemas — the multi-shot writer's structured-output contract (v3).

PIPELINE ROLE:
  StoryPitch (Stage 1, src/monitor/schemas.py, loaded from AnglePitchRecord.story_json)
  →  ContentWriter.write()  →  MultiShotPackage (this file)  →  render adapter
  (ONE prose-chained scene prompt)  →  executor (ONE Seedance generation)
  →  assembly (TTS narration + BGM + hook card + tail-fade)  →  one 10–25s 9:16 video.

WHY THIS FILE EXISTS:
  MultiShotPackage is the schema the LLM fills via structured output (in two calls —
  ShotPlanDraft is call 1's output; call 2 writes per-shot scene lines; the final
  package is assembled in code). Pydantic validation is the guard rail: a package
  that breaks the product envelope (shot count, per-shot estimate, total duration)
  is rejected, not silently rendered.

PARADIGM (motion-native scene lane, spec 2026-07-06, supersedes the still-first
  multi-shot paradigm of spec 2026-07-04):
  One video = ONE Seedance generation of 3–6 prose-chained shots, 10–25s total
  (v1 target: one 10s generation), vertical 9:16, register = SOURCE-STYLE-MATCHED.
  No per-shot model routing, no breakout shots, no Kling fallback (D3) — MotionTag
  survives as shot metadata only (a free labeled feature for P4).

  The writer's output is render-agnostic TEXT. anchors_block and style_anchor are
  package-level and composed into the scene prompt BY THE ADAPTER in code — shot
  scene lines must NOT contain them (an LLM asked to repeat an anchor verbatim
  across six lines eventually paraphrases, which is the identity-drift trigger).

  Per-shot seconds are an INTERNAL estimate (narration word-budget math only) and
  NEVER appear in prompt text (D2 — bracketed timestamps are rejected by the
  Higgsfield CLI, measured 2026-07-06). Duration reaches the model exclusively as
  the CLI --duration parameter, read from config/render_rules.yaml scene_lane.

  Narration is real TTS audio mixed at assembly; native audio keeps concrete SFX,
  music is suppressed in-prompt ("no music") and added at assembly (D5). hook_text
  is burned at assembly, never baked into a render.

  Full decision log: docs/superpowers/specs/2026-07-06-motion-native-render-refactor.md.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.monitor.schemas import BeatRole

# Product envelope (D1, 2026-07-06 motion-native spec — floor relaxed 12→10 so a
# single 10s Seedance generation validates): total runtime bounds in seconds.
TOTAL_SECONDS_MIN = 10
TOTAL_SECONDS_MAX = 25


class Register(str, Enum):
    """Visual register the whole package targets.

    source_style is the only launch value (D1): the render should read as footage
    from the SOURCE show (anime source → that show's animation language; live-action
    -styled source → that show's cinematography). The found-footage register was
    retired with the single-shot product; the enum exists so a second register can
    earn its way back without a schema break.
    """

    source_style = "source_style"


class MotionTag(str, Enum):
    """Per-shot content classification — METADATA ONLY in the scene lane (D3).

    The scene lane renders everything in one Seedance generation, so nothing
    routes on this tag. It survives as a free labeled feature for P4. Values
    remain config/render_rules.yaml `routing:` keys VERBATIM (parity enforced
    by test) so the tag vocabulary stays documented in one place.
    """

    fluid_motion = "fluid_motion"
    impossible_physics = "impossible_physics"
    transformation = "transformation"
    spectacle = "spectacle"
    character_consistency = "character_consistency"


class ShotSpec(BaseModel):
    """One render-ready shot of the final package — one per source StoryBeat.

    Attributes:
      beat_role: Copied from the source StoryBeat (hook/establish/.../payoff/tag).
      motion_tag: LLM-classified shot-content tag — metadata only (D3): nothing
        routes on it; it stays as a free labeled feature for P4.
      scene_line: Call 2's Seedance prose line for this shot — one camera move +
        one subject action (separated) + a concrete "Audio:" event. Carries NO
        anchors, NO style words, NO seconds/timestamps (D2) — the adapter chains
        lines with "Then cut to" and composes identity/style/constraints in code.
      duration_seconds: 3–8s INTERNAL estimate (narration word-budget math only);
        NEVER enters prompt text — duration reaches the model exclusively as the
        CLI --duration parameter (D2). Floor raised 2→3 (2026-07-12, sequence-craft
        plan): a 2s shot cannot fit a readable action — pitch-43's 2s/3-action
        hook rendered smeared; corpus pacing evidence in render_rules.yaml
        sequence_craft.
      narration_line: TTS narration text for this shot, or None for a silent beat
        (passthrough from StoryBeat.narration_line). Budget ≤ 2.2 words × duration.
      characters_in_frame: Copied from the source StoryBeat.
      model_cli_id: CODE-SET after parsing (never trusted from the LLM); "" until
        set. Scene lane: always the scene_lane.model from render_rules.yaml.
    """

    model_config = ConfigDict(extra="forbid")

    beat_role: BeatRole
    motion_tag: MotionTag
    scene_line: str
    duration_seconds: int = Field(ge=3, le=8)
    narration_line: str | None
    dialogue_line: str | None = None  # spoken line, copied from the source StoryBeat
    speaker: str | None = None  # who says it, copied from the source StoryBeat
    characters_in_frame: list[str]
    model_cli_id: str = ""


class ShotDraft(BaseModel):
    """Call-1 draft of one shot: classified and planned, but not yet model-native.

    motion_intent is a model-AGNOSTIC action/camera/timing/audio description; call 2
    converts it into a Seedance prose line (becoming ShotSpec.scene_line). The draft
    carries NO still_prompt — the scene lane renders no stills, so call 1 never
    spends tokens writing image prompts (dropped 2026-07-06, D4).
    """

    model_config = ConfigDict(extra="forbid")

    beat_role: BeatRole
    motion_tag: MotionTag
    motion_intent: str
    duration_seconds: int = Field(ge=3, le=8)
    narration_line: str | None
    characters_in_frame: list[str]


class ShotPlanDraft(BaseModel):
    """Call 1's full structured output: draft shots + package-level creative fields.

    Everything the LLM decides lives here; routing, consistency grouping, and
    provenance are stamped by code afterwards (spec §2.2). Same cardinality and
    duration envelope as the final package so a bad plan fails BEFORE call 2 spends
    tokens converting it.
    """

    model_config = ConfigDict(extra="forbid")

    shots: list[ShotDraft] = Field(min_length=3, max_length=5)
    style_anchor: str
    anchors_block: str
    hook_text: str | None
    caption: str
    hashtags: list[str]
    music_brief: str | None
    rationale: str | None = None

    @model_validator(mode="after")
    def _check_total_duration(self) -> "ShotPlanDraft":
        """Reject plans whose summed shot estimates leave the 10–25s product envelope (D1)."""
        total = sum(shot.duration_seconds for shot in self.shots)
        if not TOTAL_SECONDS_MIN <= total <= TOTAL_SECONDS_MAX:
            raise ValueError(
                f"total duration {total}s outside {TOTAL_SECONDS_MIN}-"
                f"{TOTAL_SECONDS_MAX}s (D1, 2026-07-06 motion-native spec)"
            )
        return self


class MultiShotPackage(BaseModel):
    """One generated video's full content kit — the writer flow's final output.

    Assembled in CODE from ShotPlanDraft + call 2's scene lines; never parsed
    whole from a single LLM response. Provenance fields (pitch_id,
    reference_image_paths) are code-set and never trusted from the LLM.

    Attributes:
      shots: 3–6 ShotSpecs, one per source StoryBeat, in beat order.
      visual_register: Visual register (source_style at launch, D1). Named
        visual_register because a bare `register` field shadows a BaseModel
        attribute (pydantic UserWarning on every import).
      style_anchor: ONE line naming the source's visual register; the adapter
        composes it into the scene prompt's style preamble in code.
      anchors_block: One identity sentence per character (name, hair, outfit category
        + primary color, recognition trait); the adapter composes it into the scene
        prompt's identity block in code, binding refs positionally ("(imageN)").
      hook_text: Hook card text (from StoryPitch.hook_line), burned at assembly via
        drawtext (D9); None = deliberately textless.
      caption: TikTok caption posted with the video.
      hashtags: Discovery tags for the post.
      music_brief: Sonilo prompt for the BGM track, or None for no score (D8).
      rationale: Optional free-text explanation of creative choices.
      pitch_id: AnglePitchRecord id this package was written from (code-set).
      reference_image_paths: Character-ref files attached to the scene generation
        (code-set; grounding is mandatory per DECISIONS_LOCKED L3). Upload order
        defines the positional "(imageN)" binding in the identity block.
      world_anchor: ~40-60 words of concrete setting nouns (materials, fixtures,
        light sources) describing the canonical location — vision-generated from
        the location screencap and cached per location, NOT writer-invented
        (spec 2026-07-10 decision #4; invention can contradict the image). The
        adapter appends it verbatim in the identity zone, byte-identical across
        the generation, mirroring style_anchor. Empty string = ungrounded setting.
      location_reference_paths: Canonical screencap(s) of the depicted setting
        (code-set), uploaded AFTER the character refs and bound as a NON-character
        "(imageN)" ref — a location is not a cast member, so these bypass the
        adapter's cast-slug crash-guard and get their own setting binding. Empty
        list = no location reference (backward-compatible with pre-grounding packages).
    """

    model_config = ConfigDict(extra="forbid")

    shots: list[ShotSpec] = Field(min_length=3, max_length=5)
    visual_register: Register = Register.source_style   # "register" bare shadows a BaseModel attr
    style_anchor: str
    anchors_block: str
    hook_text: str | None
    caption: str
    hashtags: list[str]
    music_brief: str | None
    rationale: str | None = None
    # --- code-set provenance, never trusted from the LLM ---
    pitch_id: int | None = None
    reference_image_paths: list[str] = Field(default_factory=list)
    world_anchor: str = ""
    location_reference_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_total_duration(self) -> "MultiShotPackage":
        """Reject packages whose summed shot estimates leave the 10–25s envelope (D1)."""
        total = sum(shot.duration_seconds for shot in self.shots)
        if not TOTAL_SECONDS_MIN <= total <= TOTAL_SECONDS_MAX:
            raise ValueError(
                f"total duration {total}s outside {TOTAL_SECONDS_MIN}-"
                f"{TOTAL_SECONDS_MAX}s (D1, 2026-07-06 motion-native spec)"
            )
        return self


# The legacy single-shot Shot/ContentPackage classes (2026-06-22 paradigm) were
# deleted 2026-07-05 with the Tasks 4/5 rewrites — no remaining importers.
