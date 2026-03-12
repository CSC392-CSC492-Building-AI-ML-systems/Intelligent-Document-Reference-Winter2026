"""Embedding storage model."""

from dataclasses import dataclass

import numpy as np


@dataclass
class EmbeddingRecord:
    doc_id: str
    chunk_index: int
    vector: np.ndarray
    model_name: str

    @property
    def dimension(self) -> int:
        return self.vector.shape[0]
