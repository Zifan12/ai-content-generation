import torch
from sentence_transformers import SentenceTransformer 
from abc import ABC, abstractmethod

class TextEmbedder(ABC):

    @abstractmethod 
    def embed(self, texts: list[str]) -> list[list[float]]:
        pass

    @property
    @abstractmethod
    def dim(self) -> int:
        pass 

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass 

class BgeM3Embedder(TextEmbedder):

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "auto", normalize: bool = True):
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

    
