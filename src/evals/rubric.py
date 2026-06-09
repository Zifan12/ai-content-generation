
import yaml

from src.schemas.generation import ContentPackage


def load():
    with open ("config/writer_rubric.yaml") as f:
        data = yaml.safe_load(f)
    return data["criteria"]


def select(package: ContentPackage, records: list) -> list[dict]:
    keepers = []
    
    for record in records:
        if record["scope"] == "universal":
            keepers.append(record)
        elif record["scope"] == "conditional" and record["applies_when"] == package.organizing_principle:
            keepers.append(record)
        
    return keepers