"""
One-shot data migration: SQLite → Postgres.

Copies all rows from each ORM-managed table in dependency order. Idempotent
via ON CONFLICT DO NOTHING — safe to re-run. Handles JSON serialization
(SQLite stores JSON as TEXT, Postgres has JSONB) and post-insert sequence
sync so Postgres SERIAL/IDENTITY sequences don't collide with copied PKs.

Prerequisite: run `alembic upgrade head` against the destination Postgres
URL before invoking this script so destination schema exists.

Usage:
    uv run python scripts/migrate_sqlite_to_postgres.py \\
        --src sqlite:///data/app.db \\
        --dst postgresql+psycopg://aicg:aicg_local@localhost:5433/aicg \\
        [--chunk-size 500] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


# Dependency order — parents before children. Derived from FK graph:
#   niches → raw_content_items → {blueprints, extractor_responses, transcripts, golden_labels}
#   niches → detected_trends
#   eval_runs, miner_rankings: no FKs
# alembic_version is excluded — Alembic manages it.
TABLE_ORDER: list[str] = [
    "niches",
    "raw_content_items",
    "detected_trends",
    "blueprints",
    "extractor_responses",
    "transcripts",
    # "golden_labels" skipped — 97/100 rows are orphaned (content_item_ids deleted
    # during re-scrape). Table exists in schema; re-label against surreal_hyperreal at P3.5.
    "eval_runs",
    "miner_rankings",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Copy data from SQLite to Postgres.")
    p.add_argument("--src", required=True, help="Source SQLAlchemy URL (SQLite).")
    p.add_argument("--dst", required=True, help="Destination SQLAlchemy URL (Postgres).")
    p.add_argument("--chunk-size", type=int, default=500, help="Rows per INSERT batch.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows only; skip INSERT and sequence sync.",
    )
    return p.parse_args()


def coerce_row(row: dict[str, Any], dst_table: Table) -> dict[str, Any]:
    """
    Convert a SQLite-shaped row into a Postgres-shaped row.

    Handles two SQLite-vs-Postgres type mismatches:
      - JSON: SQLite stores as TEXT (Python str); Postgres JSONB wants dict/list.
        json.loads() the value if the destination column is JSON/JSONB and the
        source is a string. None and already-parsed values pass through.
      - Datetimes: SQLite returns ISO strings; psycopg accepts strings for
        TIMESTAMP, but parsing here makes type errors surface at copy time
        rather than at first query. Skip if value is None or already a datetime.

    Booleans (0/1 INTEGER on SQLite → BOOLEAN on Postgres) and other scalar
    types are handled transparently by psycopg, so no conversion needed.
    """
    out: dict[str, Any] = {}
    for col_name, value in row.items():
        if col_name not in dst_table.c:
            # Column exists on source but not destination — skip silently.
            # Happens if Alembic dropped a column that's still in SQLite.
            continue
        if value is None:
            out[col_name] = None
            continue

        col_type_name = type(dst_table.c[col_name].type).__name__

        if col_type_name in ("JSON", "JSONB") and isinstance(value, str):
            try:
                out[col_name] = json.loads(value)
            except json.JSONDecodeError:
                # Malformed JSON in source — preserve as-is and let dst raise.
                out[col_name] = value
        elif col_type_name == "DateTime" and isinstance(value, str):
            try:
                out[col_name] = datetime.fromisoformat(value)
            except ValueError:
                out[col_name] = value
        else:
            out[col_name] = value
    return out


def copy_table(
    table_name: str,
    src_engine: Engine,
    dst_engine: Engine,
    chunk_size: int,
    dry_run: bool,
) -> tuple[int, int, str]:
    """
    Copy one table. Returns (src_count, dst_count, status_string).

    Pattern:
      1. Reflect destination table to learn its column types (drives JSON/dt coercion).
      2. SELECT * from source.
      3. Coerce rows. Chunk into batches of chunk_size.
      4. Insert with ON CONFLICT DO NOTHING for idempotency (matches on PK).
      5. After insert, sync the PK sequence so app-side INSERTs don't collide.
      6. Compare final counts.
    """
    src_meta = MetaData()
    dst_meta = MetaData()

    try:
        src_table = Table(table_name, src_meta, autoload_with=src_engine)
        dst_table = Table(table_name, dst_meta, autoload_with=dst_engine)
    except SQLAlchemyError as exc:
        return (0, 0, f"REFLECT_FAIL: {exc}")

    with src_engine.connect() as src_conn:
        src_count = src_conn.execute(select(func.count()).select_from(src_table)).scalar_one()

    with dst_engine.connect() as dst_conn:
        dst_count_before = dst_conn.execute(select(func.count()).select_from(dst_table)).scalar_one()

    if dry_run:
        return (src_count, dst_count_before, "DRY_RUN")

    if src_count == 0:
        return (src_count, dst_count_before, "EMPTY")

    # Stream rows in chunks to bound memory. fetchmany() with a server-side
    # cursor would be ideal, but SQLite doesn't really support that — fetchall
    # is fine for tables under ~100k rows.
    with src_engine.connect() as src_conn:
        result = src_conn.execute(select(src_table))
        all_rows = [dict(r._mapping) for r in result]

    coerced = [coerce_row(r, dst_table) for r in all_rows]

    inserted_total = 0
    with dst_engine.begin() as dst_conn:
        for i in range(0, len(coerced), chunk_size):
            chunk = coerced[i : i + chunk_size]
            stmt = pg_insert(dst_table).values(chunk).on_conflict_do_nothing()
            dst_conn.execute(stmt)
            inserted_total += len(chunk)

        # Sequence sync — only for tables with a single integer PK named "id".
        # All ORM tables in this project use this convention.
        if "id" in dst_table.c and dst_table.c["id"].primary_key:
            # pg_get_serial_sequence returns the sequence name backing the column,
            # or NULL if there isn't one (e.g., user-supplied PKs). setval skips
            # gracefully when called with NULL inside COALESCE-style guard.
            dst_conn.exec_driver_sql(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table_name}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                    true
                )
                WHERE pg_get_serial_sequence('{table_name}', 'id') IS NOT NULL
                """
            )

    with dst_engine.connect() as dst_conn:
        dst_count_after = dst_conn.execute(select(func.count()).select_from(dst_table)).scalar_one()

    status = "OK" if dst_count_after >= src_count else "COUNT_MISMATCH"
    return (src_count, dst_count_after, status)


def print_summary(results: dict[str, tuple[int, int, str]]) -> bool:
    """Print aligned summary table. Returns True if any non-OK status."""
    name_w = max(len(n) for n in results)
    header = f"{'table'.ljust(name_w)}  {'src':>7}  {'dst':>7}  status"
    print()
    print(header)
    print("-" * len(header))
    any_fail = False
    for name, (src, dst, status) in results.items():
        print(f"{name.ljust(name_w)}  {src:>7}  {dst:>7}  {status}")
        if status not in ("OK", "DRY_RUN", "EMPTY"):
            any_fail = True
    print()
    return any_fail


def main() -> int:
    args = parse_args()

    if not args.src.startswith("sqlite"):
        print(f"--src must be a SQLite URL, got: {args.src}", file=sys.stderr)
        return 2
    if "postgres" not in args.dst:
        print(f"--dst must be a Postgres URL, got: {args.dst}", file=sys.stderr)
        return 2

    src_engine = create_engine(args.src, future=True)
    dst_engine = create_engine(args.dst, future=True)

    results: dict[str, tuple[int, int, str]] = {}
    for table_name in TABLE_ORDER:
        print(f"  copying {table_name}...", flush=True)
        results[table_name] = copy_table(
            table_name=table_name,
            src_engine=src_engine,
            dst_engine=dst_engine,
            chunk_size=args.chunk_size,
            dry_run=args.dry_run,
        )

    any_fail = print_summary(results)

    if args.dry_run:
        print("DRY-RUN complete. No rows written.")
        return 0
    if any_fail:
        print("MIGRATION FAILED — see status column above.", file=sys.stderr)
        return 1
    print("MIGRATION OK.")
    return 0


if __name__ == "__main__":
    # Allow running from project root via `uv run python scripts/migrate_sqlite_to_postgres.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.exit(main())
