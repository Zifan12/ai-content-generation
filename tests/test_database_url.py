"""
Tests for src.database — DATABASE_URL handling per ADR-0006 (Postgres-only).

Two failure modes are asserted:
  1. DATABASE_URL unset (and no config/.env on disk) -> RuntimeError
  2. DATABASE_URL set but non-postgres scheme         -> RuntimeError

The happy path (Postgres URL) is asserted by test_postgres, which also opens a
real connection — that requires the local Postgres container to be running.
"""

import importlib

import pytest

import src.database


def test_raises_when_url_unset(monkeypatch):
    """
    With DATABASE_URL unset AND .env autoload disabled, module import must
    raise RuntimeError. Mirrors production ECS behaviour where there is no
    .env on disk and DATABASE_URL must come from the task definition.

    The stub is applied at the `dotenv.load_dotenv` source rather than the
    re-exported name in `src.database`. `importlib.reload` re-runs
    `from dotenv import load_dotenv`, so patching the import source is the
    only place the stub survives the reload.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        importlib.reload(src.database)


def test_raises_when_url_not_postgres(monkeypatch):
    """
    Per ADR-0006 the SQLite fallback was removed. Any non-postgres scheme
    must fail loud at import time so dev environments cannot silently fall
    back to a backend that lacks pgvector + ON CONFLICT DO UPDATE.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/should_not_work.db")
    with pytest.raises(RuntimeError, match="must point at Postgres"):
        importlib.reload(src.database)


def test_postgres(monkeypatch):
    """
    Happy path. Requires the local Postgres container at port 5433 to be
    running (docker compose up postgres) — skipped silently in CI if not.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://aicg:aicg_local@localhost:5433/aicg")
    importlib.reload(src.database)
    assert str(src.database.engine.url).startswith("postgresql")
    with src.database.engine.connect():
        pass
