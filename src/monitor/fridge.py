"""
The web-research "fridge": persist the raw web text the ContextAgent gathers so a
downstream stage can retrieve a specific detail on demand, instead of losing it to
the summary compression.

``index_web_text`` chunks the raw web text, embeds each chunk (BGE-M3), and writes
one :class:`WebResearchChunk` row per chunk. Chunking follows the structural-first
strategy (Huyen Ch.6, via the 2026-07-09 Second Brain consult): split on the
``\\n\\n`` block boundaries already in the text, keep the small clean search
snippets whole, and only sentence-pack the oversized full-page (firecrawl) blocks
with a little overlap so a fact never straddles a boundary. Light markdown cleanup
runs first so formatting cruft does not become junk chunks.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.web_research_chunk import WebResearchChunk

if TYPE_CHECKING:
    # Type-only import: TextEmbedder lives in a module that imports torch +
    # sentence-transformers at load time. Guarding it here keeps the pure chunker
    # (and its unit test) from paying a ~60s heavy-ML import it never uses at
    # runtime — index_web_text only duck-types the injected embedder.
    from src.rag.embedder import TextEmbedder

# Cleaned blocks shorter than this are dropped as junk (a lone nav item, a stray
# bullet left after de-markdowning).
_MIN_CHUNK_CHARS = 30
# Cleaned blocks longer than this are treated as full-page dumps and sentence-
# packed; shorter blocks are already snippet-sized and kept whole. Empirical, no
# formula (Second Brain 2026-07-09) — a conservative first cut, tune from real runs.
_BIG_BLOCK_CHARS = 1200
# Target size when packing sentences out of a big block.
_TARGET_CHUNK_CHARS = 700
# Character overlap carried between consecutive packed chunks, so a fact split at a
# boundary still appears whole in one chunk (Huyen's "I left my wife a note").
_OVERLAP_CHARS = 120
# Embed in small batches: BGE-M3 at batch=32 OOMs the local 4070 with the desktop
# open (memory: gpu_vram_budget); 8 is the safe size.
_EMBED_BATCH_SIZE = 8
# Default number of chunks a retrieve() call returns. Small suits the precision
# "find THE fact" use case; empirical, tune from real runs (no universal best).
_DEFAULT_RETRIEVE_K = 3


def _clean_block(block: str) -> str:
    """Strip light markdown formatting so cruft does not become its own chunk.

    Unwraps ``[text](url)`` links to their text, removes emphasis / heading /
    blockquote markers and leading list bullets, and collapses runs of
    whitespace. Deliberately light — it de-markdowns; it does NOT try to
    semantically detect nav/boilerplate (a rabbit hole not worth it for v1).
    """
    block = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", block)  # [text](url) -> text
    block = re.sub(r"^\s*[-+*]\s+", "", block, flags=re.MULTILINE)  # list bullets
    block = re.sub(r"[*_`#>]+", " ", block)  # md emphasis/heading/quote markers
    block = re.sub(r"\s+", " ", block)  # collapse whitespace
    return block.strip()


def _sentence_pack(block: str) -> list[str]:
    """Split a big block into sentences and greedily pack them to ~target size.

    Sentences are kept whole on the primary boundary (never cut mid-sentence);
    consecutive packed chunks share an ~``_OVERLAP_CHARS`` character tail so a
    fact at a boundary survives intact in one chunk. A single sentence longer
    than the target becomes its own (oversized) chunk — rare, and within BGE-M3's
    context.
    """
    sentences = re.split(r"(?<=[.!?])\s+", block)
    chunks: list[str] = []
    cur = ""
    for sentence in sentences:
        if cur and len(cur) + 1 + len(sentence) > _TARGET_CHUNK_CHARS:
            chunks.append(cur)
            tail = cur[-_OVERLAP_CHARS:]
            cur = f"{tail} {sentence}".strip()
        else:
            cur = f"{cur} {sentence}".strip() if cur else sentence
    if cur:
        chunks.append(cur)
    return chunks


def _chunk_web_text(raw_web_text: str) -> list[str]:
    """Chunk the concatenated raw web text into retrieval-sized pieces.

    Splits on the ``\\n\\n`` boundaries that already separate search snippets and
    page paragraphs, cleans each block, drops junk-short blocks, keeps
    snippet-sized blocks whole, and sentence-packs oversized (full-page) blocks.
    Returns the ordered list of chunk texts ready to embed.
    """
    chunks: list[str] = []
    for block in raw_web_text.split("\n\n"):
        cleaned = _clean_block(block)
        if len(cleaned) < _MIN_CHUNK_CHARS:
            continue
        if len(cleaned) > _BIG_BLOCK_CHARS:
            chunks.extend(_sentence_pack(cleaned))
        else:
            chunks.append(cleaned)
    return chunks


def index_web_text(
    topic: str,
    raw_web_text: str,
    embedder: TextEmbedder,
    session: Session,
) -> int:
    """Chunk, embed, and persist the raw web text as WebResearchChunk rows.

    Chunks ``raw_web_text`` (see :func:`_chunk_web_text`), embeds the chunks in
    VRAM-safe batches via ``embedder``, and writes one row per chunk scoped by
    ``topic``. ``embedder`` and ``session`` are injected (not created here): a
    fresh ``BgeM3Embedder`` would reload a ~2.27GB model every call, so the caller
    passes the one already loaded (wiring is Task 1.5).

    ``source_url`` is left None — the concatenated web text does not preserve
    which chunk came from which page (v1 limitation; retrieval finds the fact by
    content, not by source). Not idempotent: calling twice for the same topic
    inserts duplicate rows (v1 is within-run, called once per run).

    Returns the number of rows written (0 when the text yields no usable chunks).
    """
    chunks = _chunk_web_text(raw_web_text)
    if not chunks:
        return 0

    rows: list[WebResearchChunk] = []
    for start in range(0, len(chunks), _EMBED_BATCH_SIZE):
        batch = chunks[start : start + _EMBED_BATCH_SIZE]
        vectors = embedder.embed(batch)
        rows.extend(
            WebResearchChunk(
                topic=topic,
                chunk_text=text,
                source_url=None,
                embedding_model=embedder.model_name,
                embedding=vector,
            )
            for text, vector in zip(batch, vectors)
        )

    session.add_all(rows)
    session.commit()
    return len(rows)


def retrieve(
    topic: str,
    query: str,
    embedder: TextEmbedder,
    session: Session,
    k: int = _DEFAULT_RETRIEVE_K,
) -> list[str]:
    """Return the ``k`` chunk texts most relevant to ``query``, scoped to ``topic``.

    Embeds ``query`` with the SAME embedder used at index time (query and chunk
    vectors must share one space), then runs a pgvector cosine-nearest search over
    this topic's :class:`WebResearchChunk` rows.

    No score floor in v1: a topic with no truly relevant chunk still returns its
    ``k`` nearest (add a similarity threshold if real runs show junk). Returns
    fewer than ``k`` when the topic has fewer chunks, and ``[]`` when it has none.

    Args:
        topic: the run's topic — retrieval is scoped to rows carrying this topic.
        query: text to find relevant chunks for (typically an unsupported pitch
            claim from the Task 1.4 groundedness trigger).
        embedder: the same embedder ``index_web_text`` used (injected — sharing the
            already-loaded model avoids a ~2.27GB reload).
        session: DB session (injected).
        k: maximum number of chunks to return, nearest first.

    Returns:
        Up to ``k`` ``chunk_text`` strings, ordered nearest first.
    """
    vec = embedder.embed([query])[0]
    stmt = (
        select(WebResearchChunk.chunk_text)
        .where(WebResearchChunk.topic == topic)
        .order_by(WebResearchChunk.embedding.cosine_distance(vec))
        .limit(k)
    )
    return list(session.execute(stmt).scalars().all())
