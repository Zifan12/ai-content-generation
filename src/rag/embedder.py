"""
Text embedding layer for the P2 RAG stack.

Wraps BAAI/bge-m3 behind a swappable abstract interface so the indexer
(src/rag/indexer.py) and retriever (src/rag/retriever.py) depend on the
contract instead of the concrete model. Both sides call the same instance
so query and document vectors land in the same subspace — bi-encoder
symmetry rules out the asymmetric-encoding bugs that come with task-switched
embedders.
"""

import torch
from sentence_transformers import SentenceTransformer
from abc import ABC, abstractmethod

class TextEmbedder(ABC):
    """
    Contract for text embedders consumed by the RAG indexer and retriever.

    A swap-friendly seam: any class implementing this ABC (BGE-M3, OpenAI,
    Voyage, a future local model) can be dropped in without touching call
    sites. The dim and model_name properties are load-bearing — the indexer
    writes model_name into viral_videos.embedding_model for hash-based dedup,
    and dim must match the pgvector column width.
    """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of strings into fixed-dim float vectors.

        Returns one list of `dim` floats per input, in input order. Implementations
        must L2-normalize the output so cosine similarity reduces to a plain dot
        product downstream (pgvector `<#>` operator + offline reranking math both
        assume unit vectors).
        """
        pass

    @property
    @abstractmethod
    def dim(self) -> int:
        """
        Output vector dimensionality.

        Must match the pgvector Vector(N) column width on viral_videos.embedding.
        A swap to a different-dim model requires a migration; this property is
        how callers compile-time-ish check that.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        Stable identifier for the underlying model.

        Written into viral_videos.embedding_model at index time; combined with
        the embed-text hash to form the dedup key. Two embedders with the same
        model_name but different versions/quantizations would alias — keep
        identifiers precise (e.g. "BAAI/bge-m3", not "bge").
        """
        pass

class BgeM3Embedder(TextEmbedder):
    """
    BAAI/bge-m3 implementation of TextEmbedder via sentence-transformers.

    Native 1024-dim, MIT licensed, bi-encoder (no task switch between query
    and document encoding). Same model family as the Task 18.5 reranker,
    which simplifies the dependency surface.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "auto", normalize: bool = True):
        """
        Load BAAI/bge-m3 onto the requested device.

        device="auto" resolves to "cuda" when torch.cuda.is_available() else
        "cpu", so the same code runs on dev (GPU) and CI (no GPU) without
        edits. normalize is locked at construction (not per-call) because
        cosine-as-dot-product is a global invariant for the retrieval stack
        — flipping it per call would silently break pgvector ranking.
        First instantiation triggers a ~2.27GB HuggingFace download on cache
        miss.
        """
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"

        self._model_name = model_name
        self._normalize = normalize
        self._model = SentenceTransformer(model_name, device=device)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=self._normalize).tolist()

    @property
    def dim(self) -> int:
        return 1024

    @property
    def model_name(self) -> str:
        return self._model_name
