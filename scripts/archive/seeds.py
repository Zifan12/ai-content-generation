"""
Seed loader: parse config/archive_seeds.yaml into flat (niche, hashtag) pairs.

Each hashtag becomes one Apify run. Seeds are de-overlapped (each hashtag
assigned to exactly one niche, mega-tags like fyp/ai dropped) so the broad
scrape spends credit on maximally-distinct videos.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Seed:
    """One scrape target: a hashtag belonging to a niche."""

    niche: str
    hashtag: str


def load_seeds(path: Path, niche: str | None = None) -> list[Seed]:
    """
    Load and flatten the seed YAML into a list of Seed(niche, hashtag) pairs.

    Args:
        path: path to the seeds YAML. Expected shape::

            seeds:
              - niche: <name>
                hashtags: [<tag>, ...]

        niche: optional filter — only return seeds for this niche.

    Returns:
        Flat list of Seed in file order.

    Raises:
        FileNotFoundError: if path does not exist.
        KeyError / TypeError: if the YAML shape is malformed.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    pairs: list[Seed] = []
    for entry in data["seeds"]:
        entry_niche = entry["niche"]
        if niche is not None and entry_niche != niche:
            continue
        for tag in entry["hashtags"]:
            pairs.append(Seed(entry_niche, str(tag)))
    return pairs
