"""Persistence for the Exilus TopicBrief artifact: a per-topic, pinned fact.

``save_topic_brief`` and ``load_topic_brief`` are the one canonical read/write
path for :class:`~src.monitor.schemas.TopicBrief` against
:class:`~src.models.exilus_topic.ExilusTopicRecord` — every later stage
(research re-entry, the driver's pinning check, a future re-read/correct
flow) goes through these two functions rather than re-implementing the
find-or-create-by-topic lookup, so the REPLACE guarantee (a refresh leaves
nothing of the prior write behind) is enforced in exactly one place.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.exilus_topic import ExilusTopicRecord
from src.monitor.schemas import TopicBrief


def save_topic_brief(topic: str, brief: TopicBrief, session: Session) -> ExilusTopicRecord:
    """Write (or REPLACE) the pinned TopicBrief for ``topic``.

    Finds the topic's row by its unique ``topic`` column, creating one on
    first research pass, and OVERWRITES ``brief_json`` wholesale with
    ``brief``'s full dump. This is the artifact half of the PRD's refresh
    guarantee: a second call for the same topic replaces the column's
    content outright — there is no field-by-field merge for old content to
    survive in.

    Returns the persisted (committed) record so a caller can read back
    ``.id``/``.created_at``/``.updated_at`` without a second query.
    """
    record = session.query(ExilusTopicRecord).filter_by(topic=topic).one_or_none()
    if record is None:
        record = ExilusTopicRecord(topic=topic)
        session.add(record)
    record.brief_json = brief.model_dump(mode="json")
    session.commit()
    return record


def load_topic_brief(topic: str, session: Session) -> TopicBrief | None:
    """Read back the pinned TopicBrief for ``topic``.

    Returns ``None`` both when ``topic`` has no row yet and when it has a
    row but no brief has been written yet (``brief_json`` is NULL) — both
    are legitimate "no research done yet" states, not errors.
    """
    record = session.query(ExilusTopicRecord).filter_by(topic=topic).one_or_none()
    if record is None or record.brief_json is None:
        return None
    return TopicBrief.model_validate(record.brief_json)
