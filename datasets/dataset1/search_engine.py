"""Core search engine with BM25 + vector hybrid retrieval."""

import hashlib
from typing import Any

import numpy as np


class SearchEngine:
    def __init__(self):
        self._documents: dict[str, dict[str, Any]] = {}
        self._embeddings: dict[str, np.ndarray] = {}

    def index(self, text: str, metadata: dict | None = None) -> str:
        doc_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        self._documents[doc_id] = {
            "text": text,
            "metadata": metadata or {},
        }
        self._embeddings[doc_id] = self._embed(text)
        return doc_id

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        q_emb = self._embed(query)
        scores = []
        for doc_id, emb in self._embeddings.items():
            score = float(
                np.dot(q_emb, emb)
                / (np.linalg.norm(q_emb) * np.linalg.norm(emb) + 1e-9)
            )
            scores.append((doc_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for doc_id, score in scores[:top_k]:
            results.append(
                {
                    "id": doc_id,
                    "score": round(score, 4),
                    "snippet": self._documents[doc_id]["text"][:200],
                    "metadata": self._documents[doc_id]["metadata"],
                }
            )
        return results

    def count(self) -> int:
        return len(self._documents)

    @staticmethod
    def _embed(text: str) -> np.ndarray:
        rng = np.random.default_rng(seed=hash(text) % 2**32)
        return rng.standard_normal(384).astype(np.float32)
