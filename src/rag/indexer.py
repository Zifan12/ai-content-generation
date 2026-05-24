"""
Blueprint-aware indexer over the corpus.

Writes vector representations of (BlueprintRecord, RawContentItem, Transcript)
joins into the viral_videos table. Hash-based dedup avoids re-embedding rows
whose serialized text and embedding model have not changed — every cron tick
and every smoke run would otherwise pay full embedding cost.
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from src.models.transcript import Transcript
from src.models.blueprint import BlueprintRecord
from src.models.trend import RawContentItem
from src.models.viral_video import ViralVideo
from src.rag.embedder import TextEmbedder
from src.rag.serialization import serialize_for_embed, embed_text_hash


def index_corpus(db: Session,
                 embedder: TextEmbedder,
                 extractor_version: str = "v3.1",
                 only_missing: bool = True,
                 batch_size: int = 32,
                ) -> dict:
    """
    Embed every (BlueprintRecord, RawContentItem) pair at the given extractor_version
    and upsert into viral_videos.

    Args:
        db: SQLAlchemy session. Caller owns the lifecycle; this function does not close.
        embedder: Implementation of TextEmbedder. Tests inject a fake; production uses BgeM3Embedder.
        extractor_version: Blueprint schema version to filter by. Different versions live side-by-side
            in the blueprints table; this argument locks one generation per index pass.
        only_missing: When True (default), skip rows whose existing viral_videos entry already has the
            same embed_text_hash AND embedding_model. Set False to force re-embed (model swap, serializer
            bug fix, etc.).
        batch_size: Texts per embedder.embed() call. Bounded by GPU VRAM, not corpus size.

    Returns:
        {"considered": int, "skipped_same_hash": int, "embedded": int, "elapsed_seconds": float}.
        Invariant: considered == skipped_same_hash + embedded.
    """

    start = time.perf_counter()
    considered = 0
    embedded = 0
    skipped_same_hash = 0

    # OUTER join — transcripts are optional (subtitle URLs expire ~30 days; some videos never had them).
    # INNER join would silently drop blueprints with no transcript row, undercounting `considered`.
    rows = db.execute(
        select(BlueprintRecord, RawContentItem, Transcript)
        .join(RawContentItem, BlueprintRecord.content_item_id == RawContentItem.id)
        .outerjoin(Transcript, Transcript.content_item_id == RawContentItem.id)
        .where(BlueprintRecord.extractor_version == extractor_version)
    ).all()

    pending = []
    for blueprint, raw, transcript_row in rows:
        considered += 1

        description = raw.description
        hashtags = raw.hashtags
        transcript = transcript_row.text if transcript_row is not None else None
        blueprint_data = blueprint.blueprint_data

        embed_str = serialize_for_embed(description=description, hashtags=hashtags, transcript=transcript, blueprint_data=blueprint_data)
        embed_hash = embed_text_hash(embed_str)

        if only_missing:
            existing = db.execute(
                select(ViralVideo)
                .where(ViralVideo.content_item_id == raw.id)
            ).scalar_one_or_none()

            if existing is not None and existing.embed_text_hash == embed_hash and existing.embedding_model == embedder.model_name:
                skipped_same_hash += 1
                continue 
            
        pending.append((raw.id, blueprint.id, embed_str, embed_hash))


    for i in range(0, len(pending), batch_size):
        chunk = pending[i : i + batch_size]
        texts = [c[2] for c in chunk]
        vectors = embedder.embed(texts)

        for (content_item_id, blueprint_id, text, embed_hash), vec in zip(chunk, vectors):
            data = {
                "content_item_id": content_item_id,
                "blueprint_id": blueprint_id,
                "embedding_model": embedder.model_name,
                "embedding_dim": embedder.dim,
                "embed_text_hash": embed_hash, 
                "embedding": vec
            }
            stmt = (
                insert(ViralVideo).values(**data)
                .on_conflict_do_update(index_elements=["content_item_id"], set_={k: v for k, v in data.items() if k != "content_item_id"})
            )

            db.execute(stmt)
            embedded += 1
            
    db.commit()
    elapsed_seconds = time.perf_counter() - start

    return {
        "considered": considered,
        "skipped_same_hash": skipped_same_hash,
        "embedded": embedded, 
        "elapsed_seconds": elapsed_seconds
    }


