"""BlueprintRetriever: vector similarity search over indexed Blueprint corpus.

Takes a BlueprintCandidate from the miner, serializes it to the same embed-input
format used at index time, and queries pgvector for the nearest neighbors.
Without this, the generation layer has no grounded examples to condition on.
"""

from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.blueprint import BlueprintRecord
from src.models.viral_video import ViralVideo
from src.rag.embedder import TextEmbedder
from src.rag.serialization import serialize_candidate_for_query
from src.rag.schemas import RetrievalQuery, RetrievalHit, RetrievalResponse


class BlueprintRetriever:
    """Retrieves similar BlueprintRecords from pgvector given a BlueprintCandidate query."""

    def __init__(self, db: Session, embedder: TextEmbedder, extractor_version: str = "v3.1"):
        self._db = db 
        self._embedder = embedder
        self._extractor_version = extractor_version


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

        stmt = (
            select(BlueprintRecord, ViralVideo.embedding.cosine_distance(vec).label("dist"))
            .join(ViralVideo, BlueprintRecord.content_item_id == ViralVideo.content_item_id)
            .where(BlueprintRecord.extractor_version == self._extractor_version)
            .order_by(ViralVideo.embedding.cosine_distance(vec))
            .limit(query.top_k)
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

        elapsed_ms = (perf_counter() - t0) * 1000.
       
        return RetrievalResponse(query=query, hits=hits, elapsed_ms=elapsed_ms)