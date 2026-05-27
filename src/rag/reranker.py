"""Stage-2 cross-encoder reranking for the Blueprint RAG retriever.

Bi-encoder embedding (stage 1) scores query and doc separately and misses
fine-grained interactions — negation, exact-word matches, subtle topic shifts.
Cross-encoder joint-attends over [query, doc] in one forward pass, catching
those signals at the cost of per-pair inference. Used as the precision stage
over K=20 vector candidates; never used alone (would not scale to corpus).
"""
import torch
from sentence_transformers import CrossEncoder
from src.rag.schemas import RetrievalHit
from abc import ABC, abstractmethod


class Reranker(ABC):
    """Abstract base for cross-encoder rerankers.

    Concrete implementations receive a query string and a list of stage-1 hits,
    score each (query, doc) pair jointly, and return the top_n hits sorted by
    reranker score. Implementations MUST overwrite each hit's `.score` field
    with the reranker output — downstream consumers see precision-stage ranking,
    not stage-1 cosine.
    """

    @abstractmethod
    def rerank(self, query: str, candidates: list[RetrievalHit], top_n: int) -> list[RetrievalHit]:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass


class BgeRerankerV2M3(Reranker):
    """Cross-encoder wrapper around BAAI/bge-reranker-v2-m3 via sentence-transformers.

    Same XLM-RoBERTa-large backbone as the BGE-M3 embedder, trained with a
    pairwise relevance head. Output is a raw logit (NOT cosine, NOT probability)
    — sort descending within one query, never compare across queries.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str = "auto", batch_size: int = 8):
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
        
        self._model_name = model_name
        self._model = CrossEncoder(model_name, device=device)
        self._batch_size = batch_size

    @property
    def model_name(self) -> str:
        return self._model_name
    
    def rerank(self, query: str, candidates: list[RetrievalHit], top_n: int) -> list[RetrievalHit]:
        """Score each candidate jointly with the query, return top_n by reranker score.

        Mutates input candidates in place: each candidate's `.score` is overwritten
        with the cross-encoder logit (replaces stage-1 cosine). Caller's list reflects
        reranked order after this returns.
        """
        pairs = []
        for candidate in candidates:
            pairs.append((query, candidate.serialized_text))

        scores = self._model.predict(inputs=pairs, batch_size=self._batch_size)

        for cand, score in zip(candidates, scores):
            cand.score = float(score)

        candidates.sort(key=lambda x: x.score, reverse=True)

        return candidates[:top_n]


