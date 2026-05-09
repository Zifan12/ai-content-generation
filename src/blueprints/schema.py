"""
Blueprint Pydantic schema and locked taxonomies.

`EXTRACTOR_VERSION` is the cache key for stored extractions in the
`blueprints` table — bump it whenever the schema or prompt changes so old and
new extractions remain distinguishable.
"""

from typing import Literal

from pydantic import BaseModel, Field

EXTRACTOR_VERSION = "v1"


# Locked taxonomies (theory-grounded; not affected by bootstrap)
StructureStage = Literal[
    "hook", "setup", "tension", "escalation", "twist",
    "demo", "reveal", "payoff", "cta", "loop",
]

PrimaryEmotion = Literal[
    "awe", "surprise", "tension", "humor", "anger",
    "anxiety", "aspiration", "satisfaction", "relatability",
]

DurationBand = Literal[
    "under_10s", "10_20s", "20_40s", "40_60s", "over_60s",
]

# v1 taxonomies (bootstrapped 2026-05-09 from 120 v0 BlueprintRecord rows)
# Source of truth: docs/taxonomy/v1_enums.md
FormatType = Literal[
    "ai_generated", "tutorial", "talking_head", "storytime_narration",
    "horror_story", "meme_remix", "compilation", "aesthetic_showcase",
    "animation", "reaction", "transformation",
]

HookType = Literal[
    "shocking_claim", "curiosity_gap", "visual_pattern_break", "visual_aesthetic",
    "character_intro", "emotional_hook", "pattern_interrupt", "direct_promise",
]

PayoffType = Literal[
    "reveal", "twist", "humor", "emotional_resolution",
    "aesthetic_satisfaction", "informational", "call_to_action",
]


class Blueprint(BaseModel):
    """
    18-field viral-mechanics summary of a single video.
    """

    format: FormatType
    format_subtype: str | None = None

    hook_type: HookType
    hook_subtype: str | None = None

    payoff_type: PayoffType
    payoff_subtype: str | None = None

    structure: list[StructureStage]
    primary_emotion: PrimaryEmotion
    duration_band: DurationBand

    hook_strength: float = Field(ge=0.0, le=1.0)
    curiosity_gap: float = Field(ge=0.0, le=1.0)
    immediate_clarity: float = Field(ge=0.0, le=1.0)
    emotional_charge: float = Field(ge=0.0, le=1.0)
    payoff_quality: float = Field(ge=0.0, le=1.0)
    replayability: float = Field(ge=0.0, le=1.0)
    comment_trigger: float = Field(ge=0.0, le=1.0)
    shareability: float = Field(ge=0.0, le=1.0)

    extractor_version: str
    extractor_model: str
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None