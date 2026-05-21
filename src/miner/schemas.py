"""Pydantic contracts for the mechanic miner pipeline.

MinerEvidence and BlueprintCandidate are the typed data contracts
that flow between candidate selection, ranking, storage, and RAG
retrieval. Keeping them here (not in rank.py) lets storage and
retriever import shapes without pulling in ranking logic.
"""
from pydantic import BaseModel, field_validator, Field
from typing import Any

class MinerEvidence(BaseModel):
    """Aggregate statistics for one mechanic combo (e.g. hook_type+pacing+audio_type).

    Produced by the grouping step in rank.py; consumed by BlueprintCandidate.
    trend_slope_4wk_pct is allowed to be negative — a declining combo is
    still valid evidence, just ranked lower by the composite score.
    """
    matching_items: int = Field(ge=1)
    median_views: int = Field(ge=0)           
    p90_views: int = Field(ge=0)               
    trend_slope_4wk_pct: float    
    rationale: str = Field(min_length=1)   

class BlueprintCandidate(BaseModel):
    """A ranked mechanic combo with supporting evidence.

    blueprint_template holds only the fields the miner grouped on —
    not the full Blueprint — so the RAG retriever can embed a clean,
    signal-only query vector without noise from free-text fields.
    """
    rank: int = Field(ge=1)
    niche_label: str = Field(min_length=1)            
    blueprint_template: dict[str, Any]
    evidence: MinerEvidence

    @field_validator("blueprint_template")
    @classmethod
    def at_least_one_field(cls, v):
        if not v:
            raise ValueError("blueprint_template must have >=1 field")
        return v