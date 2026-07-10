"""Tests for the web-research fridge: pure chunker + DB-backed retrieve."""

import hashlib

import numpy as np
import pytest
from sqlalchemy.orm import Session

from src.database import engine
from src.monitor.fridge import (
    _TARGET_CHUNK_CHARS,
    _chunk_web_text,
    index_web_text,
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
