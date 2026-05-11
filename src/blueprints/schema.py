"""
Blueprint Pydantic schema (v3, niche-agnostic) and locked taxonomies.

`EXTRACTOR_VERSION` is the cache key for stored extractions in the
`blueprints` table — bump it whenever the schema or prompt changes so old and
new extractions remain distinguishable.
"""

from typing import Literal

from pydantic import BaseModel, Field

EXTRACTOR_VERSION = "v3"


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


class Blueprint(BaseModel):
    """Niche-agnostic two-tier Blueprint (v3)."""

    hook_type: str
    primary_emotion: PrimaryEmotion
    share_hook_type: str
    comment_bait_type: str
    pacing: str
    loop_type: str
    audio_type: str
    visual_complexity: str
    color_mood: str
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