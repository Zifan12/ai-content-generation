"""Load the v0 rubric criteria from YAML and select which apply to a given package."""

import yaml

from src.schemas.generation import ContentPackage


def load():
    """Read the criteria list from the v0 rubric YAML."""
    with open ("config/writer_rubric.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["criteria"]


def select(package: ContentPackage, records: list) -> list[dict]:
    """Keep the universal criteria plus conditional ones whose applies_when matches the package's organizing_principle."""
    keepers = []
    
    for record in records:
        if record["scope"] == "universal":
            keepers.append(record)
        elif record["scope"] == "conditional" and record["applies_when"] == package.organizing_principle:
            keepers.append(record)
        
    return keepers