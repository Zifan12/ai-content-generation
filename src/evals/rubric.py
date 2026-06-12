"""Load the v0 rubric criteria from YAML and select which apply to a given package."""

import yaml

from src.schemas.generation import ContentPackage


def load():
    """Read the criteria list from the v0 rubric YAML."""
    with open ("config/writer_rubric.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["criteria"]


def select(package: ContentPackage, records: list) -> list[dict]:
    """
    Select the rubric criteria that apply to a given package.

    Always keeps every criterion whose scope is "universal". For "conditional"
    criteria, keeps the ones whose applies_when matches the package's device. A
    conditional criterion's applies_when may be a single device string OR a list of
    devices (some rules apply to several change-devices at once — e.g. the event-beat
    rule fires for both transformation and time_compression), so the match must treat
    a scalar and a list uniformly. Returns the kept criterion records in input order.
    """
    keepers = []

    for record in records:
        if record["scope"] == "universal":
            keepers.append(record)
        elif record["scope"] == "conditional":
            applies_when = record["applies_when"]
            allowed_devices = applies_when if isinstance(applies_when, list) else [applies_when]
            if package.device in allowed_devices:
                keepers.append(record)

    return keepers