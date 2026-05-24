"""
SQLAlchemy engine, session factory, and Base for the project.

DATABASE_URL is read strictly from the process environment. The module auto-loads
config/.env at the repo root before reading the env var, but only when the var is
not already set (override=False) — so production AWS task definitions that set
DATABASE_URL directly take precedence over any local file.

If DATABASE_URL is missing or does not point at Postgres, this module fails at
import time with a clear message. The prior SQLite fallback was removed per
docs/adr/0006-drop-sqlite-postgres-only.md — pgvector, ON CONFLICT DO UPDATE, and
HNSW indexing make Postgres the only viable backend for P2+ work.
"""

import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / "config" / ".env"

# Auto-load config/.env only when DATABASE_URL is not already set. Production
# AWS sets the env var directly; this is a no-op there. Local dev / pytest /
# ad-hoc `python -c` invocations get the var without each call site reimplementing
# the dotenv load.
if not os.environ.get("DATABASE_URL") and _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)


DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Either run via `uv run ...` (which loads "
        "config/.env automatically) or ensure config/.env exists at the repo "
        "root with a DATABASE_URL= line. See docs/adr/0006-drop-sqlite-postgres-only.md."
    )

if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        f"DATABASE_URL must point at Postgres (got scheme: "
        f"{DATABASE_URL.split('://', 1)[0]!r}). SQLite fallback was removed per "
        f"docs/adr/0006-drop-sqlite-postgres-only.md."
    )


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    future=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,   # Don't auto-send changes to DB — we control when to flush
    autocommit=False,   # Require explicit commits
    expire_on_commit=False,  # Keep objects usable after commit without re-querying
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session and ensures it's closed
    after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
