"""Document retrieval service."""

import numpy as np


class RetrieverService:
    def __init__(self, db, embedder):
        self.db = db
        self.embedder = embedder

    def search(self, query: str, top_k: int = 5):
        q_emb = self.embedder.embed(query)
        candidates = self.db.get_all_embeddings()
        scores = []
        for record in candidates:
            sim = np.dot(q_emb, record.vector) / (
                np.linalg.norm(q_emb) * np.linalg.norm(record.vector) + 1e-9
            )
            scores.append((record, float(sim)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
