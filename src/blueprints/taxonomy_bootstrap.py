"""
Historical script: bootstrap v1 taxonomy from v0 open-string values.

**STATUS: LEGACY** — This script ran once during v0→v1 transition (early 2026).
Kept for reference only. Current version is v3 (niche-agnostic schema).

WHAT IT DID (past tense):
  v0 extractor stored free-text labels for format/hook_type/payoff_type. Before
  promoting to v1, those labels needed to collapse to a tight enum (~10 mechanics
  per field, not 1000+ unique strings). This script asked Claude to cluster v0
  values, produced a proposal for human review, then those clusters became v1 enums.

WHY IT'S NOT USED NOW:
  v1 enums are now baked into the schema. v3 evolved beyond v1 with niche
  conditioning (universal + niche-specific fields). Taxonomy expansion now
  happens in prompts, not via bootstrapping scripts.

KEEPING IT:
  Preserved for audit trail + potential future re-clustering if v3 enums
  need evolutionary bumps. Also demonstrates the taxonomy methodology.

"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select

from src.database import SessionLocal
from src.models.blueprint import BlueprintRecord
from src.providers.llm.anthropic_llm import AnthropicLLM  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

class Cluster(BaseModel):
    name: str
    members: list[str]

class ClusterProposal(BaseModel):
    field: str 
    clusters: list[Cluster]

SYSTEM_PROMPT = """You are organizing free-text labels into a tight taxonomy. \
Group the labels into 8-15 clusters per field. Use snake_case names that describe \
the underlying mechanic (not just a synonym). Every input label must appear in exactly \
one cluster. Output structured JSON only."""

def fetch_distinct_values(field: str, version: str ="v0") -> list[str]:
    """
    Return all non-empty values for `field` across Blueprints at `version`.

    Falsy values (None, "") are dropped — v0 marks unknown mechanics as None
    and feeding them to the clusterer pollutes the proposal.
    """
    db = SessionLocal()
    try:
        records = db.scalars(
            select(BlueprintRecord).where(BlueprintRecord.extractor_version==version)
        ).all()

        values = [r.blueprint_data.get(field) for r in records if r.blueprint_data.get(field)]
        return values
    finally:
        db.close()


def main():
    """
    Fetch v0 distinct values for one field, send to LLM for clustering,
    print/save the JSON proposal for human review.
    """
    parser = argparse.ArgumentParser(description="Cluster v0 open-string values into v1 enum proposals.")
    # Only v0 fields stored as open strings; other Blueprint fields already closed enums.
    parser.add_argument("--field", choices=["format", "hook_type", "payoff_type"], required=True)
    parser.add_argument("--source-version", default="v0")
    parser.add_argument("--output", default=None, help="Write JSON proposal here")
    args = parser.parse_args()

    values = fetch_distinct_values(args.field, args.source_version)
    counts = Counter(values)
    log.info("Field=%s source=%s | %d records, %d distinct values",
             args.field, args.source_version, len(values), len(counts))
    log.info("Top 20: %s", counts.most_common(20))

    distinct = sorted(counts.keys())
    # Need ≥3 distinct labels for cluster proposal to be meaningful (8-15 target groups).
    if len(distinct) < 3:
        raise SystemExit("Not enough distinct values to cluster (need ≥3).")

    llm = AnthropicLLM(model="claude-sonnet-4-6")

    prompt=(
        f"Field: {args.field}\n\n"
        f"Distinct labels (with frequency):\n"
        + "\n".join(f"  {label} ({counts[label]})" for label in distinct)
        + "\n\nGroup these into 8-15 clusters. Pick a snake_case name per cluster. "
        f"Every label must go in exactly one cluster. Field name: {args.field}."
    )

    proposal = llm.parse(prompt=prompt, response_model=ClusterProposal, system=SYSTEM_PROMPT, max_tokens=2048)
 
    out = json.dumps(proposal.model_dump(), indent=2)
    print(out)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        log.info("Saved to %s", args.output)

if __name__ == "__main__":
    main()