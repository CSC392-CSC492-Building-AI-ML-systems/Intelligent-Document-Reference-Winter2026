"""Tests for Voyage embedding client."""

import os
from pathlib import Path

import numpy as np
import pytest

from model_clients.voyage_client import VoyageEmbeddingClient

pytestmark = pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VOYAGE_API_KEY is not set; skipping live Voyage integration test.",
)


def cosine_similarity(emb1, emb2):
    """Calculate cosine similarity between two embeddings.

    Args:
        emb1: First embedding vector.
        emb2: Second embedding vector.

    Returns:
        Cosine similarity score between -1 and 1.
    """
    emb1_array = np.array(emb1)
    emb2_array = np.array(emb2)

    dot_product = np.dot(emb1_array, emb2_array)
    norm1 = np.linalg.norm(emb1_array)
    norm2 = np.linalg.norm(emb2_array)

    if norm1 == 0 or norm2 == 0:
        raise ValueError("Cannot compute cosine similarity: zero vector detected")

    return dot_product / (norm1 * norm2)


def test_banana_text_image_similarity():
    """Test that text 'This is a banana' is more similar to banana image than apple image."""
    # Initialize client
    client = VoyageEmbeddingClient()

    # Get repository root (Intelligent-Document-Reference-Winter2026/)
    # From test file: tests/unit/test_voyage_client.py -> up 3 levels to repo root
    repo_root = Path(__file__).parent.parent.parent
    fixtures_dir = repo_root / "tests" / "fixtures"
    banana_image_path = fixtures_dir / "banana.jpg"

    # Get apple image path
    apple_image_path = fixtures_dir / "apple.jpeg"

    # Check if images exist, skip test if they don't
    if not banana_image_path.exists():
        pytest.skip(f"Banana image not found at {banana_image_path}")
    if not apple_image_path.exists():
        pytest.skip(f"Apple/comparison image not found at {apple_image_path}")

    # Embed text
    text = "This is a banana"
    text_embeddings = client.embed_text([text])
    text_embedding = text_embeddings[0]

    # Embed banana image
    banana_embeddings = client.embed_image([str(banana_image_path)])
    banana_embedding = banana_embeddings[0]

    # Embed apple/comparison image
    apple_embeddings = client.embed_image([str(apple_image_path)])
    apple_embedding = apple_embeddings[0]

    # Compute cosine similarities
    banana_similarity = cosine_similarity(text_embedding, banana_embedding)
    apple_similarity = cosine_similarity(text_embedding, apple_embedding)

    # Assert that banana similarity is higher than apple similarity
    assert banana_similarity > apple_similarity, (
        f"Banana similarity ({banana_similarity:.4f}) should be higher than "
        f"apple similarity ({apple_similarity:.4f})"
    )
