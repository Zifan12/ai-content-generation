"""Unit tests for the web-research fridge chunker (pure, no DB / no embedder)."""

from src.monitor.fridge import _TARGET_CHUNK_CHARS, _chunk_web_text


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
