import importlib
import os

import pytest
import src.database

def test_sqlite_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(src.database)
    assert "sqlite" in str(src.database.engine.url)

def test_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://aicg:aicg_local@localhost:5433/aicg")
    importlib.reload(src.database)
    assert str(src.database.engine.url).startswith("postgresql")
    with src.database.engine.connect():
        pass