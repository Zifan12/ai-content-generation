# Drop SQLite fallback; Postgres-only with fail-loud config

`src/database.py` defaults `DATABASE_URL` to a SQLite file when the env var is unset, then branches on URL scheme for engine creation. The pattern was useful in P0/P1 when no Docker dependency was desirable. By P2 the trade-off has inverted: pgvector, JSON-column behavior, `ON CONFLICT DO UPDATE`, and HNSW indexing are Postgres-only features now baked into the schema (Task 14 migration `7a492259a3c1` skips half its body on SQLite). The fallback is a silent footgun — code that reads `raw_content_items` runs against either backend, while code touching `viral_videos` crashes only after the SQL parser reaches an unknown table. The two surface as different failure modes for the same root cause.

This ADR records the decision to remove the SQLite path entirely and to fail loud when `DATABASE_URL` is missing or non-Postgres, plus an auto-load of `config/.env` so that local dev entry points (REPL, `python -c`, ad-hoc scripts) reach Postgres without each one re-implementing the dotenv dance.

## Trigger

During Task 17 implementation (`src/rag/indexer.py`, P2 RAG plan) two separate ad-hoc invocations silently picked up SQLite:

1. `.venv/Scripts/python.exe -m pytest tests/test_rag_indexer.py` — pytest does not run through `uv` and never called `load_dotenv`. Engine bound to `sqlite:///data/app.db`. Test crashed at `no such table: viral_videos` *after* seeding 10 rows into the wrong database.
2. `.venv/Scripts/python.exe -c "..."` smoke for Task 17 step 4 — same root cause, same crash signature.

Workaround for (1) was a new `tests/conftest.py` that calls `load_dotenv` before any test module imports `src.database`. Workaround for (2) was a one-shot `$env:DATABASE_URL = "..."` in PowerShell. Both are patches around the same hole. Every future entry point that touches the DB will hit this until the default is removed.

## Decision

1. **`src/database.py` reads `DATABASE_URL` strictly.** No default. If the env var is unset or its value does not begin with `postgresql`, raise `RuntimeError` with a message pointing at the fix: "Set DATABASE_URL via `uv run`, or ensure config/.env exists at repo root."
2. **`src/database.py` auto-loads `config/.env` before reading the env var,** but only when `DATABASE_URL` is not already set in the process environment and the file exists. Uses `python-dotenv`'s `override=False` so an explicitly-set env var (e.g. production AWS task definition) always wins.
3. **All other `load_dotenv("config/.env")` calls are removed** from application code: `src/api/app.py`, `src/miner/rank.py`, `src/blueprints/taxonomy_bootstrap.py`. The dotenv load now lives in exactly one place — the module that owns the env-var contract.
4. **`tests/conftest.py` is deleted.** Its only purpose was the same dotenv hack; with (2) above it becomes dead weight.
5. **The stale `data/app.db` SQLite file is removed** (gitignored, never committed; just hygiene).
6. **`DB_PATH` and the `data/` `mkdir` boilerplate are removed** from `src/database.py`.

## Consequences

- **No more silent backend switching.** Every entry point either reaches Postgres or crashes immediately at module-load time with an actionable message. Prior behavior — "writes to SQLite, fails 30 seconds later when an unfamiliar table is hit" — is gone.
- **Single source of truth for `DATABASE_URL`.** Production (AWS ECS Fargate) sets the env var directly; the auto-load is a no-op there. Local dev relies on `config/.env`. CI (planned, P7) sets the env var in the workflow file.
- **`uv run pytest` workaround for the script-canonicalization bug becomes less critical.** Tests now reach Postgres regardless of which Python launcher invokes them, as long as `config/.env` is present at repo root.
- **One-way door for SQLite.** If a future feature requires a SQLite path (e.g. fully-offline demo), it ships behind a deliberate feature flag or a new env-var convention, not by reverting this ADR.
- **Migration files keep their `if dialect.name == "postgresql"` guards** for now. Removing them is a separate cleanup; this ADR does not touch Alembic.

## Rollback

If the strict mode causes friction (e.g. a contributor without Docker can't even import `src.database`), the rollback is straightforward: restore the SQLite default in `src/database.py` and re-add a clear warning to the top of the file. The dotenv auto-load can stay either way. The ADR itself is reverted via a new ADR-0007 ("Restore SQLite fallback") so the decision trail remains intact.

## Considered alternatives

**Keep the SQLite default but log a warning when it fires** — rejected because warnings without enforcement get ignored, and the cost signal (silent wrong-DB writes) is high enough that a hard fail is the right tool.

**Move the dotenv load into each entry point individually (keep status quo)** — rejected because every new script becomes a chance to re-introduce the silent fallback. The four existing scripts already prove that pattern doesn't scale.

**Use `pydantic-settings` instead of `python-dotenv`** — out of scope. The current config story uses `dotenv` already; switching to pydantic-settings is a separate refactor with its own trade-offs (typed config, validation, etc.). This ADR is the minimal fix.

**Add a `tests/conftest.py` as the permanent solution** — rejected because the failure mode applies outside tests (the Task 17 smoke crash hit `python -c`, not pytest). The fix has to live in `src/database.py` to cover all callers.
