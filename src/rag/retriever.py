"""BlueprintRetriever: vector similarity search over indexed Blueprint corpus.

Takes a BlueprintCandidate from the miner, serializes it to the same embed-input
format used at index time, and queries pgvector for the nearest neighbors.
Without this, the generation layer has no grounded examples to condition on.
"""

from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.transcript import Transcript
from src.models.trend import RawContentItem
from src.models.blueprint import BlueprintRecord
from src.models.viral_video import ViralVideo
from src.rag.embedder import TextEmbedder
from src.rag.reranker import Reranker
from src.rag.serialization import serialize_candidate_for_query, serialize_for_embed
from src.rag.schemas import RetrievalQuery, RetrievalHit, RetrievalResponse


class BlueprintRetriever:
    """Retrieves similar BlueprintRecords from pgvector given a BlueprintCandidate query."""

    def __init__(self, 
                 db: Session, 
                 embedder: TextEmbedder, 
                 extractor_version: str = "v3.1", 
                 reranker: Reranker | None = None, 
                 stage_1_k: int = 20):
        
        self._db = db 
        self._embedder = embedder
        self._extractor_version = extractor_version
        self._reranker = reranker
        self._stage_1_k = stage_1_k


    def retrieve(self, query: RetrievalQuery) -> RetrievalResponse:
        """Query pgvector for blueprints nearest to the serialized candidate.

        Serializes the candidate to embed-input text, embeds it, runs a cosine-distance
        ANN query against viral_videos.embedding, joins BlueprintRecord, and returns hits
        sorted by similarity descending.

        Args:
            query: RetrievalQuery with candidate blueprint template and top_k limit.

        Returns:
            RetrievalResponse with hits sorted by score descending and wall-clock elapsed_ms.
        """
        t0 = perf_counter()

        text = serialize_candidate_for_query(candidate=query.candidate)
        vec = self._embedder.embed([text])[0]

        k = query.top_k

        if self._reranker is not None:
            k = self._stage_1_k
            if query.top_k > self._stage_1_k:
                raise ValueError
        
        stmt = (
            select(BlueprintRecord, ViralVideo.embedding.cosine_distance(vec).label("dist"))
            .join(ViralVideo, BlueprintRecord.content_item_id == ViralVideo.content_item_id)
            .where(BlueprintRecord.extractor_version == self._extractor_version)
            .order_by(ViralVideo.embedding.cosine_distance(vec))
            .limit(k)
        )

        rows = self._db.execute(stmt).all()

        hits = [
            RetrievalHit(
                content_item_id=blueprint_record.content_item_id,
                blueprint_id=blueprint_record.id,
                score=1.0 - dist,
                blueprint_data=blueprint_record.blueprint_data,
                niche_label=blueprint_record.blueprint_data.get("niche_label", "unknown")
            ) 
            for blueprint_record, dist in rows
        ]

        if self._reranker is not None:
            ids = [h.content_item_id for h in hits]

            hydration_stmt = (
                select(RawContentItem.description, RawContentItem.hashtags, RawContentItem.id, Transcript.text)
                .join(Transcript, RawContentItem.id == Transcript.content_item_id)
                .where(RawContentItem.id.in_(ids))
            )

            rows = self._db.execute(hydration_stmt).all()

            lookup = {content_item_id: (description, hashtags, transcript) for description, hashtags, content_item_id, transcript in rows }

            for hit in hits:
                description, hashtags, transcript = lookup[hit.content_item_id]
                hit.serialized_text = serialize_for_embed(description=description,hashtags=hashtags, transcript=transcript, blueprint_data=hit.blueprint_data)

            hits = self._reranker.rerank(query=text, candidates=hits, top_n=query.top_k)

        elapsed_ms = (perf_counter() - t0) * 1000.
       
        return RetrievalResponse(query=query, hits=hits, elapsed_ms=elapsed_ms)
    

    