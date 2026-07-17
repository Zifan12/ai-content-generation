"""Tests for the web-research fridge: pure chunker + DB-backed retrieve."""

import hashlib

import numpy as np
import pytest
from sqlalchemy.orm import Session

from sqlalchemy import select

from src.database import engine
from src.models.web_research_chunk import WebResearchChunk
from src.monitor.fridge import (
    _TARGET_CHUNK_CHARS,
    _chunk_web_text,
    index_web_text,
    replace_topic_material,
    retrieve,
)


def test_chunk_keeps_snippets_whole_splits_big_drops_junk():
    """The chunker keeps snippet blocks whole, drops junk-short blocks, and
    sentence-packs an oversized block into multiple bounded chunks."""
    snippet = "Wistoria season 2 finale aired and fans loved the throne-room fight."
    junk = "*"  # a lone markdown bullet -> empty after cleaning -> dropped
    big = (
        " ".join(
            f"Sentence number {i} about the finale and the two lead characters."
            for i in range(60)
        )
    )
    raw = f"{snippet}\n\n{junk}\n\n{big}"

    chunks = _chunk_web_text(raw)

    # snippet kept whole (appears verbatim as its own chunk)
    assert snippet in chunks
    # junk block dropped entirely
    assert all("Sentence" not in c or "finale" in c for c in chunks)
    assert not any(set(c) <= {"*", " "} for c in chunks)
    # big block split into several bounded chunks
    big_chunks = [c for c in chunks if "Sentence number" in c]
    assert len(big_chunks) >= 2
    assert all(len(c) <= _TARGET_CHUNK_CHARS + 300 for c in big_chunks)


def test_empty_text_yields_no_chunks():
    """Empty or whitespace-only input produces no chunks."""
    assert _chunk_web_text("") == []
    assert _chunk_web_text("\n\n   \n\n") == []


class _FakeEmbedder:
    """Duck-typed embedder for tests: deterministic seeded vectors, no torch.

    Not a TextEmbedder subclass on purpose — subclassing would import the real
    embedder module (torch + sentence-transformers), which the fridge only
    duck-types anyway. Same text always yields the same 1024-dim vector, so a
    query identical to an indexed chunk retrieves it exactly (cosine distance 0).
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
            vectors.append(np.random.default_rng(seed).standard_normal(1024).tolist())
        return vectors

    @property
    def model_name(self) -> str:
        return "fake-embedder"


@pytest.fixture
def db():
    """Transactional session rolled back after each test (mirrors tests/rag)."""
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    trans.rollback()
    connection.close()


def test_retrieve_scopes_by_topic_and_ranks_nearest(db):
    """retrieve returns only the queried topic's chunks, nearest first."""
    emb = _FakeEmbedder()
    alpha = "alpha chunk discussing the dragons of the northern realm and their hoard."
    beta = "beta chunk discussing the ancient castles along the rocky coast."
    gamma = "gamma chunk discussing spaceships drifting in deep orbit above."

    assert index_web_text("topic-A", f"{alpha}\n\n{beta}", emb, db) == 2
    assert index_web_text("topic-B", gamma, emb, db) == 1

    hits = retrieve("topic-A", alpha, emb, db, k=5)

    # topic-B's chunk never leaks into a topic-A query
    assert gamma not in hits
    # an exact-text query self-retrieves first (distance 0)
    assert hits[0] == alpha
    # only topic-A's two chunks are reachable
    assert len(hits) == 2


def test_retrieve_empty_topic_returns_empty(db):
    """A topic with no indexed chunks returns an empty list, not an error."""
    assert retrieve("unseen-topic", "anything", _FakeEmbedder(), db) == []


def test_upvote_tags_survive_chunking():
    """Reddit-shaped `[POST | N upvotes]` / `[COMMENT | N upvotes]` tags come
    through the same chunker verbatim (AC2) — _clean_block's regexes only touch
    markdown link/emphasis/bullet syntax, never the bracket characters."""
    reddit_block = (
        "[POST | 244 upvotes] Fans debate the finale twist\n"
        "  [COMMENT | 37 upvotes] I did not expect that reveal at all."
    )
    chunks = _chunk_web_text(reddit_block)
    assert any("[POST | 244 upvotes]" in c and "[COMMENT | 37 upvotes]" in c for c in chunks)


def test_replace_topic_material_indexes_both_sources_retrievable(db):
    """AC1: reddit-only and web-only content for one topic are both indexed and
    separately retrievable by a query matching only one source's content."""
    emb = _FakeEmbedder()
    reddit_text = "[POST | 100 upvotes] The dragon-riders finally reunite on screen."
    web_text = "A wiki summary explains the kingdom's ancient naval treaty in detail."

    written = replace_topic_material("topic-mixed", web_text, reddit_text, emb, db)
    assert written == 2

    # k=1 (not 5): with only 2 chunks total, a wide k would return both rows for
    # either query regardless of relevance — asserting the nearest hit proves the
    # query actually discriminated by content, not merely that both rows exist.
    reddit_hits = retrieve("topic-mixed", reddit_text, emb, db, k=1)
    web_hits = retrieve("topic-mixed", web_text, emb, db, k=1)
    assert reddit_hits == [reddit_text]
    assert web_hits == [web_text]


def test_replace_topic_material_replaces_not_stacks(db):
    """AC3: a second replace leaves only the second run's chunk count — the
    first run's rows are gone, not just outnumbered."""
    emb = _FakeEmbedder()
    first_reddit = "[POST | 10 upvotes] First run reddit content about the show."
    first_web = "First run web content describing the show's setting."
    replace_topic_material("topic-refresh", first_web, first_reddit, emb, db)

    second_reddit = "[POST | 20 upvotes] Second run reddit content, totally different."
    written = replace_topic_material("topic-refresh", "", second_reddit, emb, db)

    count = db.execute(
        select(WebResearchChunk).where(WebResearchChunk.topic == "topic-refresh")
    ).scalars().all()
    assert len(count) == written
    assert not any("First run" in row.chunk_text for row in count)


def test_replace_topic_material_scoped_to_one_topic(db):
    """AC4: refreshing topic A never deletes or alters topic B's rows."""
    emb = _FakeEmbedder()
    replace_topic_material("topic-A", "web A content about castles.", "", emb, db)
    replace_topic_material(
        "topic-B", "", "[POST | 5 upvotes] reddit B content about spaceships.", emb, db
    )

    # Refresh topic A again — topic B must be untouched.
    replace_topic_material("topic-A", "new web A content about castles again.", "", emb, db)

    b_rows = db.execute(
        select(WebResearchChunk).where(WebResearchChunk.topic == "topic-B")
    ).scalars().all()
    assert len(b_rows) == 1
    assert "spaceships" in b_rows[0].chunk_text


def test_replace_topic_material_empty_source_does_not_block_other(db):
    """AC6: one empty source contributes 0 rows without erroring or blocking
    the other source's indexing."""
    emb = _FakeEmbedder()
    written = replace_topic_material(
        "topic-empty-reddit", "only web content here, nothing from reddit.", "", emb, db
    )
    assert written == 1

    written = replace_topic_material(
        "topic-empty-web", "", "[POST | 8 upvotes] only reddit content here.", emb, db
    )
    assert written == 1
