"""Exercises the exilus_topics migration's upgrade()/downgrade() against the
real dev Postgres (mirrors the repo's Postgres-only stance, ADR-0006 — no
sqlite fallback for the migration itself, only for the ORM-level persistence
tests in test_exilus_topic.py).

Runs downgrade-then-upgrade starting from head (this migration is expected to
already be applied) and always leaves the DB back at head, even on failure,
so the run cannot strand a shared dev database mid-migration.
"""

import logging
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from src.database import engine

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(_REPO_ROOT / "alembic.ini"))


@contextmanager
def _preserve_logger_disabled_flags():
    """Snapshots every registered logger's ``.disabled`` flag and restores it
    on exit.

    alembic's ``env.py`` calls ``logging.config.fileConfig(...)`` with its
    default ``disable_existing_loggers=True``. That call disables every
    logger already present in ``logging.Logger.manager.loggerDict`` at the
    time it runs (e.g. ``src.monitor.story_pitcher``'s module logger, once
    that module has been imported anywhere in the process) and leaves them
    disabled for the rest of the interpreter's life. Running the alembic
    migration commands in-process, as this test does, was silently killing
    ``logger.warning`` calls in unrelated modules for the remainder of the
    pytest session. Wrapping the alembic calls in this context manager
    restores every logger's prior ``.disabled`` state afterward so this
    test's use of alembic has no observable side effect on other tests.
    """
    logger_dict = logging.Logger.manager.loggerDict
    disabled_before = {
        name: logger.disabled
        for name, logger in logger_dict.items()
        if isinstance(logger, logging.Logger)
    }
    try:
        yield
    finally:
        for name, was_disabled in disabled_before.items():
            logger = logger_dict.get(name)
            if isinstance(logger, logging.Logger):
                logger.disabled = was_disabled


def test_downgrade_drops_table_upgrade_recreates_it():
    cfg = _alembic_config()
    inspector = inspect(engine)
    assert "exilus_topics" in inspector.get_table_names(), (
        "exilus_topics must already be migrated to head before this test runs "
        "(uv run alembic upgrade head)"
    )

    with _preserve_logger_disabled_flags():
        try:
            command.downgrade(cfg, "-1")
            inspector = inspect(engine)
            assert "exilus_topics" not in inspector.get_table_names()
        finally:
            command.upgrade(cfg, "head")

    inspector = inspect(engine)
    assert "exilus_topics" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("exilus_topics")}
    assert columns == {
        "id",
        "topic",
        "brief_json",
        "faction_map_json",
        "created_at",
        "updated_at",
    }
