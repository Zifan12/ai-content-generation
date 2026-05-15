"""
Blueprint extractor cost report.

Reads usage columns from ``extractor_responses`` and prints token volume and
dollar cost broken down by niche, model, or date. Used to track how prompt
caching reduces spend across batch runs and to verify cost expectations
before large backfills.

Pricing constants are hardcoded for Claude Sonnet 4.x (per million tokens):
  input            $3.00
  output           $15.00
  cache write 1h   $6.00     (2x input)
  cache read       $0.30     (0.1x input)

If pricing changes or other models are introduced, update PRICE_PER_M_TOKENS.

Usage:
  uv run python scripts/extractor_cost_report.py
  uv run python scripts/extractor_cost_report.py --group-by niche
  uv run python scripts/extractor_cost_report.py --group-by date
  uv run python scripts/extractor_cost_report.py --since 2026-05-01
  uv run python scripts/extractor_cost_report.py --niche surreal_hyperreal
  uv run python scripts/extractor_cost_report.py --format json
"""

import argparse
import json
import logging
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.database import SessionLocal  # noqa: E402
from src.models.extractor_response import ExtractorResponse  # noqa: E402
from src.models.niche import Niche  # noqa: E402
from src.models.trend import RawContentItem  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


PRICE_PER_M_TOKENS = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 6.00,
    "cache_read": 0.30,
}


def cost(tokens: int | None, price_per_m: float) -> float:
    """Return dollar cost for ``tokens`` at the given per-million rate. None == 0."""
    return (tokens or 0) / 1_000_000 * price_per_m


def aggregate_row(rows: list[ExtractorResponse]) -> dict:
    """Sum token columns across a group of rows and compute derived costs.

    Returns a dict with raw token totals, per-bucket dollar cost, total spend,
    a hypothetical "no_cache" cost (treating cache reads as full-price inputs),
    and absolute / percent savings vs. that hypothetical.
    """
    input_tokens = sum((r.usage_input_tokens or 0) for r in rows)
    output_tokens = sum((r.usage_output_tokens or 0) for r in rows)
    cache_write_tokens = sum((r.usage_cache_write_tokens or 0) for r in rows)
    cache_read_tokens = sum((r.usage_cache_read_tokens or 0) for r in rows)

    cost_input = cost(input_tokens, PRICE_PER_M_TOKENS["input"])
    cost_output = cost(output_tokens, PRICE_PER_M_TOKENS["output"])
    cost_write = cost(cache_write_tokens, PRICE_PER_M_TOKENS["cache_write"])
    cost_read = cost(cache_read_tokens, PRICE_PER_M_TOKENS["cache_read"])
    total = cost_input + cost_output + cost_write + cost_read

    no_cache_input = input_tokens + cache_write_tokens + cache_read_tokens
    no_cache_total = (
        cost(no_cache_input, PRICE_PER_M_TOKENS["input"]) + cost_output
    )
    savings = no_cache_total - total
    pct_saved = (savings / no_cache_total * 100) if no_cache_total > 0 else 0.0

    return {
        "rows": len(rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cost_input": cost_input,
        "cost_output": cost_output,
        "cost_cache_write": cost_write,
        "cost_cache_read": cost_read,
        "total_cost": total,
        "no_cache_cost": no_cache_total,
        "savings": savings,
        "pct_saved": pct_saved,
    }


def fetch_rows(
    db: Session,
    niche_name: str | None,
    since: datetime | None,
) -> list[tuple[ExtractorResponse, str | None, datetime | None]]:
    """Return joined (ExtractorResponse, niche_name, created_at) tuples filtered by CLI args.

    Joins to RawContentItem and Niche so callers can group by niche without N+1.
    Niche may be None for items without an assigned niche_id.
    """
    stmt = (
        select(ExtractorResponse, Niche.name, ExtractorResponse.created_at)
        .join(RawContentItem, ExtractorResponse.content_item_id == RawContentItem.id)
        .outerjoin(Niche, RawContentItem.niche_id == Niche.id)
    )
    if niche_name:
        stmt = stmt.where(Niche.name == niche_name)
    if since:
        stmt = stmt.where(ExtractorResponse.created_at >= since)
    return list(db.execute(stmt).all())


def group_rows(
    joined: list[tuple[ExtractorResponse, str | None, datetime | None]],
    group_by: str,
) -> dict[str, list[ExtractorResponse]]:
    """Bucket joined rows by the requested dimension. Keys preserve the dimension value."""
    buckets: dict[str, list[ExtractorResponse]] = defaultdict(list)
    for resp, niche_name, created_at in joined:
        if group_by == "niche":
            key = niche_name or "(no niche)"
        elif group_by == "model":
            key = resp.model or "(unknown)"
        elif group_by == "date":
            key = created_at.date().isoformat() if created_at else "(no date)"
        else:
            key = "all"
        buckets[key].append(resp)
    return buckets


def format_table(buckets: dict[str, dict], group_by: str) -> str:
    """Render aggregated buckets as a fixed-width text table with totals footer."""
    header = (
        f"{'Group':<25} {'Rows':>6} "
        f"{'Input':>10} {'Output':>10} {'CacheW':>10} {'CacheR':>10} "
        f"{'Spent $':>10} {'NoCache $':>10} {'Saved $':>10} {'Saved %':>8}"
    )
    sep = "-" * len(header)
    lines = [f"Cost report grouped by: {group_by}", "", header, sep]

    totals = defaultdict(int)
    totals_money = defaultdict(float)

    for key, agg in sorted(buckets.items()):
        lines.append(
            f"{key:<25} {agg['rows']:>6} "
            f"{agg['input_tokens']:>10,} {agg['output_tokens']:>10,} "
            f"{agg['cache_write_tokens']:>10,} {agg['cache_read_tokens']:>10,} "
            f"{agg['total_cost']:>10.4f} {agg['no_cache_cost']:>10.4f} "
            f"{agg['savings']:>10.4f} {agg['pct_saved']:>7.1f}%"
        )
        for col in ("rows", "input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"):
            totals[col] += agg[col]
        for col in ("total_cost", "no_cache_cost", "savings"):
            totals_money[col] += agg[col]

    lines.append(sep)
    total_pct = (
        totals_money["savings"] / totals_money["no_cache_cost"] * 100
        if totals_money["no_cache_cost"] > 0
        else 0.0
    )
    lines.append(
        f"{'TOTAL':<25} {totals['rows']:>6} "
        f"{totals['input_tokens']:>10,} {totals['output_tokens']:>10,} "
        f"{totals['cache_write_tokens']:>10,} {totals['cache_read_tokens']:>10,} "
        f"{totals_money['total_cost']:>10.4f} {totals_money['no_cache_cost']:>10.4f} "
        f"{totals_money['savings']:>10.4f} {total_pct:>7.1f}%"
    )
    return "\n".join(lines)


def parse_since(value: str | None) -> datetime | None:
    """Parse YYYY-MM-DD CLI date into a midnight-aligned datetime, or None if absent."""
    if value is None:
        return None
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day)


def main():
    parser = argparse.ArgumentParser(description="Report Blueprint extractor token cost.")
    parser.add_argument(
        "--group-by",
        choices=["niche", "model", "date", "none"],
        default="niche",
        help="Dimension for grouping. Default: niche.",
    )
    parser.add_argument("--niche", help="Filter to a single niche name (e.g. surreal_hyperreal).")
    parser.add_argument("--since", help="Filter to rows created on or after YYYY-MM-DD.")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    args = parser.parse_args()

    since = parse_since(args.since)

    db = SessionLocal()
    try:
        joined = fetch_rows(db, niche_name=args.niche, since=since)
        if not joined:
            log.warning("No extractor_responses rows match the filters. Nothing to report.")
            return

        buckets = group_rows(joined, args.group_by)
        agg = {key: aggregate_row(rows) for key, rows in buckets.items()}

        if args.format == "json":
            print(json.dumps(agg, indent=2))
        else:
            print(format_table(agg, args.group_by))
    finally:
        db.close()


if __name__ == "__main__":
    main()
