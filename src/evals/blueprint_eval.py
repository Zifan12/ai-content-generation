"""
Blueprint-extractor eval primitives.

Self-agreement (Cohen's kappa on enums, MAE on mechanic floats) and schema-
validity rate. Without these the LLM extractor drifts silently — every prompt
edit needs a measurable signal.
"""

from typing import Iterable

from pydantic import ValidationError

from src.blueprints.schema import Blueprint
from src.models.blueprint import BlueprintRecord

import math 
import numpy as np
from sklearn.metrics import cohen_kappa_score

# v3 closes only two enums (primary_emotion, duration_band). Other Tier 1 fields
# (hook_type, share_hook_type, comment_bait_type, pacing, loop_type, audio_type,
# visual_complexity, color_mood) ship as open str and lock in v3.1 — kappa scoring
# returns for them in v3.1. See ADR-0002.
ENUM_FIELDS = ["primary_emotion", "duration_band"]

def schema_valid_rate(records: Iterable[BlueprintRecord]) -> float:
    """
    Compute fraction of BlueprintRecords whose blueprint_data validates against the Blueprint schema.

    Returns float in [0.0, 1.0], or NaN when records is empty.
    Raises nothing — ValidationError is caught per-record and counted as invalid.
    """
    # NaN signals "no data" rather than "all invalid" so callers can distinguish the two cases
    if not records:
        return float("nan")
    
    counter = 0
    for r in records:
        try:
            Blueprint.model_validate(r.blueprint_data)
            counter += 1
        except ValidationError:
            continue 
    
    return counter/len(records)

def cohen_kappa_pairs(a: list[str], b: list[str]) -> float:
    """
    Cohen's kappa between two label lists (paired). NaN on empty.
    """
    if not a or not b or len(a) != len(b):
        return float("nan")
    return float(cohen_kappa_score(a, b))
    

def mae_pairs(a: list[float], b: list[float]) -> float:
    """
    Mean absolute error between paired float lists. NaN on empty/length-mismatch.
    """
    if not a or not b or len(a) != len(b):
        return float("nan")
    return float(np.mean(np.abs(np.array(a)-np.array(b))))

