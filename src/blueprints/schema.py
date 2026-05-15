"""
Blueprint Pydantic schema (v3, niche-agnostic) and locked taxonomies.

`EXTRACTOR_VERSION` is the cache key for stored extractions in the
`blueprints` table — bump it whenever the schema or prompt changes so old and
new extractions remain distinguishable.
"""

from typing import Literal

from pydantic import BaseModel, Field

EXTRACTOR_VERSION = "v3.1"


PrimaryEmotion = Literal[
    "awe",
    "surprise",
    "tension",
    "humor",
    "anger",
    "anxiety",
    "aspiration",
    "satisfaction",
    "relatability",
]

DurationBand = Literal[
    "under_10s",
    "10_20s",
    "20_40s",
    "40_60s",
    "over_60s",
]

HookType = Literal[
    "visual_shock",
    "identity_signal",
    "curiosity_gap",
    "uncanny_reveal",
    "nostalgia_trigger",
]

ShareHookType = Literal[
    "technical_awe",
    "shocking",
    "identity_signal",
    "makes_friends_laugh",
]

CommentBaitType = Literal[
    "relatable_moment",
    "controversial_claim",
    "open_ending",
    "question_to_viewer",
]

Pacing = Literal[
    "moderate",
    "slow_atmospheric",
    "fast",
]

LoopType = Literal[
    "none",
    "hard_cut",
    "seamless_visual",
    "narrative_loop",
]

AudioType = Literal[
    "trending_audio",
    "original_voiceover",
    "ambient_sfx",
    "music_only",
]

VisualComplexity = Literal[
    "moderate",
    "minimal",
    "dense",
]

ColorMood = Literal[
    "vivid_saturated",
    "desaturated",
    "warm_muted",
    "cool_clinical",
    "neon",
]


class Blueprint(BaseModel):
    """Niche-agnostic two-tier Blueprint (v3.1 — 8 Tier 1 fields locked to Literal per ADR-0003)."""

    hook_type: HookType
    primary_emotion: PrimaryEmotion
    share_hook_type: ShareHookType
    comment_bait_type: CommentBaitType
    pacing: Pacing
    loop_type: LoopType
    audio_type: AudioType
    visual_complexity: VisualComplexity
    color_mood: ColorMood
    duration_band: DurationBand
    aesthetic_descriptors: list[str] = Field(
        description=(
            "Free-text snake_case visual/tonal descriptors. Dual use: RAG retrieval signal + prompt fragments."
        )
    )
    niche_label: str
    hook_subtype: str | None = None

    extractor_version: str
    extractor_model: str
    notes: str | None = None