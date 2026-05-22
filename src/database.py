"""
SQLAlchemy engine, session factory, and Base for the project.

DATABASE_URL env var controls which backend is used — SQLite (default, backward-compat)
or Postgres (P2+ with pgvector). Engine kwargs branch on URL scheme so callers never
need to know which backend is active. SessionLocal, Base, and get_db interface unchanged.
"""

import os
from pathlib import Path
from typing import Generator


from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # unconditional — harmless on Postgres, required on SQLite for first-run setup

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, future=True)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10, future=True)


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
    FastAPI dependency that provides a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try: 
        yield db 
    finally:
        db.close()