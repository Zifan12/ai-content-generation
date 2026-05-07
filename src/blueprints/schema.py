"""
Blueprint Pydantic schema and locked taxonomies.

`EXTRACTOR_VERSION` is the cache key for stored extractions in the
`blueprints` table — bump it whenever the schema or prompt changes so old and
new extractions remain distinguishable.
"""

from typing import Literal

from pydantic import BaseModel, Field

EXTRACTOR_VERSION = "v0"


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


class Blueprint(BaseModel):
    """
    18-field viral-mechanics summary of a single video.
    """
    
    # Open-string in v0; closed Literal[...] in v1 after taxonomy bootstrap.
    format: str
    format_subtype: str | None = None

    hook_type: str
    hook_subtype: str | None = None

    payoff_type: str
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