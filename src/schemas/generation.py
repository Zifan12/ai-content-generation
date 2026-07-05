"""
Content generation schemas — the multi-shot writer's structured-output contract (v3).

PIPELINE ROLE:
  StoryPitch (Stage 1, src/monitor/schemas.py, loaded from AnglePitchRecord.story_json)
  →  ContentWriter.write()  →  MultiShotPackage (this file)  →  render adapter
  (grouped RenderJobs)  →  executor (grounded stills + i2v / Kling multi-shot)
  →  assembly (concat + TTS narration + BGM + hook card)  →  one 12–25s 9:16 video.

WHY THIS FILE EXISTS:
  MultiShotPackage is the schema the LLM fills via structured output (in two calls —
  see spec §2.2: ShotPlanDraft is call 1's output; the final package is assembled in
  code after routing + call 2). Pydantic validation is the guard rail: a package that
  breaks the product envelope (shot count, per-shot duration, total duration) is
  rejected, not silently rendered.

PARADIGM (multi-shot source-style, spec 2026-07-04, extends content spec 2026-06-27 §4/§5):
  One video = 3–6 shots, one per StoryBeat, 12–25s total, vertical 9:16, register =
  SOURCE-STYLE-MATCHED (reads as footage from the source show; found-footage retired).
  Per-shot model routing via MotionTag (values = config/render_rules.yaml routing keys
  VERBATIM — the router calls rules.route(tag.value) with no mapping layer).

  The writer's output is render-agnostic TEXT. anchors_block and style_anchor are
  package-level and composed into prompts BY THE ADAPTER in code (D10) — shot prompts
  must NOT contain them (an LLM asked to repeat an anchor verbatim across six prompts
  eventually paraphrases, which is the identity-drift trigger).

  Narration is real TTS audio mixed at assembly (D7); there is no on-camera dialogue
  field at launch (06-27 §4 bans lip-sync). hook_text is burned at assembly (D9),
  never baked into a render.

  Full decision log: docs/superpowers/specs/2026-07-04-multishot-writer-render-redesign.md §5.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.monitor.schemas import BeatRole

# Product envelope (06-27 spec §4): total assembled runtime bounds in seconds.
TOTAL_SECONDS_MIN = 12
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
    """Per-shot content classification the router consumes (D4/D5).

    Values are config/render_rules.yaml `routing:` keys VERBATIM, so
    rules.route(tag.value) needs no mapping layer — parity is enforced by test.
    The writer classifies WHAT the shot needs; code decides WHICH model renders it.
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
      motion_tag: LLM-classified shot-content tag; the router maps it to a model.
      still_prompt: Image prompt for this shot's grounded opening still. Carries NO
        anchors and NO style words — the adapter prepends anchors_block and appends
        style_anchor + global constraints in code (D10).
      motion_prompt: Model-native i2v prompt — camera + subject action + timing +
        a concrete "Audio:" line ONLY (i2v rule: never re-describe the still).
        For shots inside a Kling consistency group this is the per-shot line the
        adapter labels `Shot N (Xs-Ys):` (native grammar, spike-proven 2026-07-04).
      duration_seconds: 4–8s (DECISIONS_LOCKED L2 clip cap).
      narration_line: TTS narration text for this shot, or None for a silent beat
        (passthrough from StoryBeat.narration_line). Budget ≤ 2.2 words × duration.
      characters_in_frame: Copied from the source StoryBeat.
      model_cli_id: CODE-SET by the router after parsing (never trusted from the
        LLM); "" until routed.
    """

    model_config = ConfigDict(extra="forbid")

    beat_role: BeatRole
    motion_tag: MotionTag
    still_prompt: str
    motion_prompt: str
    duration_seconds: int = Field(ge=4, le=8)
    narration_line: str | None
    characters_in_frame: list[str]
    model_cli_id: str = ""


class ShotDraft(BaseModel):
    """Call-1 draft of one shot: classified and planned, but not yet model-native.

    motion_intent is a model-AGNOSTIC action/camera/timing/audio description; call 2
    converts it into the routed model's dialect (becoming ShotSpec.motion_prompt).
    still_prompt IS final here — the still model (nano_banana_2) never varies, so the
    still dialect is model-independent and call 1 can finish it.
    """

    model_config = ConfigDict(extra="forbid")

    beat_role: BeatRole
    motion_tag: MotionTag
    still_prompt: str
    motion_intent: str
    duration_seconds: int = Field(ge=4, le=8)
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

    shots: list[ShotDraft] = Field(min_length=3, max_length=6)
    style_anchor: str
    anchors_block: str
    hook_text: str | None
    caption: str
    hashtags: list[str]
    music_brief: str | None
    rationale: str | None = None

    @model_validator(mode="after")
    def _check_total_duration(self) -> "ShotPlanDraft":
        """Reject plans whose summed shot durations leave the 12–25s product envelope."""
        total = sum(shot.duration_seconds for shot in self.shots)
        if not TOTAL_SECONDS_MIN <= total <= TOTAL_SECONDS_MAX:
            raise ValueError(
                f"total duration {total}s outside {TOTAL_SECONDS_MIN}-"
                f"{TOTAL_SECONDS_MAX}s (06-27 spec §4)"
            )
        return self


class MultiShotPackage(BaseModel):
    """One generated video's full content kit — the writer flow's final output.

    Assembled in CODE from ShotPlanDraft + router output + call 2's dialect
    conversions; never parsed whole from a single LLM response. Provenance fields
    (pitch_id, reference_image_paths, consistency_groups) are code-set and never
    trusted from the LLM.

    Attributes:
      shots: 3–6 ShotSpecs, one per source StoryBeat, in beat order.
      visual_register: Visual register (source_style at launch, D1). Named
        visual_register because a bare `register` field shadows a BaseModel
        attribute (pydantic UserWarning on every import).
      style_anchor: ONE line naming the source's visual register; adapter appends it
        verbatim to EVERY still prompt.
      anchors_block: One identity sentence per character (name, hair, outfit category
        + primary color, recognition trait); adapter prepends it verbatim to EVERY
        still prompt (SHOT_CRAFT consistency rule, composed in code per D10).
      hook_text: Hook card text (from StoryPitch.hook_line), burned at assembly via
        drawtext (D9); None = deliberately textless.
      caption: TikTok caption posted with the video.
      hashtags: Discovery tags for the post.
      music_brief: Sonilo prompt for the BGM track, or None for no score (D8).
      rationale: Optional free-text explanation of creative choices.
      pitch_id: AnglePitchRecord id this package was written from (code-set).
      reference_image_paths: Key-art files fed to the still model for grounding
        (code-set; grounding is mandatory per DECISIONS_LOCKED L3).
      consistency_groups: Router-computed shot-index groups; each inner list renders
        as ONE Kling multi-shot generation (D6). Singletons for breakout shots.
    """

    model_config = ConfigDict(extra="forbid")

    shots: list[ShotSpec] = Field(min_length=3, max_length=6)
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
    consistency_groups: list[list[int]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_total_duration(self) -> "MultiShotPackage":
        """Reject packages whose summed shot durations leave the 12–25s envelope."""
        total = sum(shot.duration_seconds for shot in self.shots)
        if not TOTAL_SECONDS_MIN <= total <= TOTAL_SECONDS_MAX:
            raise ValueError(
                f"total duration {total}s outside {TOTAL_SECONDS_MIN}-"
                f"{TOTAL_SECONDS_MAX}s (06-27 spec §4)"
            )
        return self


# The legacy single-shot Shot/ContentPackage classes (2026-06-22 paradigm) were
# deleted 2026-07-05 with the Tasks 4/5 rewrites — no remaining importers.
