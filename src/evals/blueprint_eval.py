from typing import Iterable

from pydantic import ValidationError

from src.blueprints.schema import Blueprint
from src.models.blueprint import BlueprintRecord


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

