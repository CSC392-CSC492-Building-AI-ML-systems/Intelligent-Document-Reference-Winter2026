"""Abstract client interfaces for embeddings and inference."""

from abc import ABC, abstractmethod
from typing import List


class EmbeddingClient(ABC):
    @abstractmethod
    def embed_text(self, texts: List[str]):
        raise NotImplementedError


class InferenceClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs):
        raise NotImplementedError
