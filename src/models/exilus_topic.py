from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ExilusTopicRecord(Base):
    """One row per named topic the Exilus front-end has researched.

    ``topic`` is the operator-named subject (character, show, game, arc — no
    freshness requirement, unlike :class:`TrendingEventRecord` which is tied
    to a scraped headline/subreddit/virality window). It is UNIQUE so a
    topic's pinned artifacts always resolve to exactly one row: the PRD's
    "refresh REPLACES rather than stacks" guarantee is implemented as an
    UPDATE against this row (find-or-create by ``topic``, overwrite the JSON
    column), never as an INSERT of a duplicate row for the same topic.

    ``brief_json`` holds the pinned :class:`~src.monitor.schemas.TopicBrief`
    (research stage, ticket 02). NULL means no research has completed for
    this topic yet.

    ``faction_map_json`` holds the pinned FactionMap (audience-camp stage,
    ticket 06). NULL means no faction read has completed yet. The column is
    created here, in ticket 01's migration, so the whole table lands in one
    migration (ticket 05 adds no migration of its own) — but ticket 01 only
    reserves the column; ticket 05 owns writing and reading it.

    ``updated_at`` advances on every UPDATE via SQLAlchemy's ``onupdate``
    (applied client-side when the ORM issues the UPDATE, not a DB trigger),
    so a refresh's write time is visible without a second query.
    """

    __tablename__ = "exilus_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    brief_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    faction_map_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
