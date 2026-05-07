"""
SQLAlchemy engine, session factory, and Base for the project.

SQLite for local dev (single-file under data/app.db); the URL is the only
thing that needs to change to swap in RDS Postgres in prod.
"""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    # SQLite only allows access from the thread that created it by default.
    # FastAPI handles requests across multiple threads, so we disable this check.
    connect_args={"check_same_thread": False},
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
    FastAPI dependency that provides a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try: 
        yield db 
    finally:
        db.close()