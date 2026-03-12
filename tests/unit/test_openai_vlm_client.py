"""Tests for OpenAI Vision Language Model client."""

import os
from pathlib import Path

import pytest

from model_clients.openai_client import OpenAIInferenceClient

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY is not set; skipping live OpenAI integration tests.",
)


def test_banana_image_recognition():
    """Test that VLM correctly identifies banana in the image.

    This is a sanity check that asks the VLM "what fruit is in the image"
    using the banana image fixture and verifies the response contains "banana".
    """
    # Initialize client
    client = OpenAIInferenceClient()

    # Get repository root (Intelligent-Document-Reference-Winter2026/)
    # From test file: tests/unit/test_openai_vlm_client.py -> up 3 levels to repo root
    repo_root = Path(__file__).parent.parent.parent
    fixtures_dir = repo_root / "tests" / "fixtures"
    banana_image_path = fixtures_dir / "banana.jpg"

    # Check if image exists, skip test if it doesn't
    if not banana_image_path.exists():
        pytest.skip(f"Banana image not found at {banana_image_path}")

    # Ask the VLM what fruit is in the image
    prompt = "what fruit is in the image"
    response = client.generate(
        prompt=prompt, images=[str(banana_image_path)], temperature=0.7, max_tokens=100
    )

    # Verify response contains "banana" (case-insensitive)
    assert response is not None, "Response should not be None"
    assert len(response) > 0, "Response should not be empty"
    assert (
        "banana" in response.lower()
    ), f"Expected response to contain 'banana', but got: {response}"


def test_banana_image_recognition_with_different_temperatures():
    """Test VLM with different temperature settings.

    Verifies that the inference function accepts dynamic temperature parameters
    and still correctly identifies the banana.
    """
    # Initialize client
    client = OpenAIInferenceClient()

    # Get repository root
    repo_root = Path(__file__).parent.parent.parent
    fixtures_dir = repo_root / "tests" / "fixtures"
    banana_image_path = fixtures_dir / "banana.jpg"

    # Check if image exists, skip test if it doesn't
    if not banana_image_path.exists():
        pytest.skip(f"Banana image not found at {banana_image_path}")

    # Test with different temperature values
    temperatures = [0.0, 0.5, 1.0, 1.5]

    for temperature in temperatures:
        prompt = "what fruit is in the image"
        response = client.generate(
            prompt=prompt,
            images=[str(banana_image_path)],
            temperature=temperature,
            max_tokens=100,
        )

        # Verify response is valid and contains "banana"
        assert (
            response is not None
        ), f"Response should not be None for temperature {temperature}"
        assert (
            len(response) > 0
        ), f"Response should not be empty for temperature {temperature}"
        assert "banana" in response.lower(), (
            f"Expected response to contain 'banana' for temperature {temperature}, "
            f"but got: {response}"
        )


def test_vlm_with_additional_parameters():
    """Test VLM with various dynamic parameters.

    Verifies that the inference function accepts and uses additional parameters
    like top_p, frequency_penalty, and presence_penalty.
    """
    # Initialize client
    client = OpenAIInferenceClient()

    # Get repository root
    repo_root = Path(__file__).parent.parent.parent
    fixtures_dir = repo_root / "tests" / "fixtures"
    banana_image_path = fixtures_dir / "banana.jpg"

    # Check if image exists, skip test if it doesn't
    if not banana_image_path.exists():
        pytest.skip(f"Banana image not found at {banana_image_path}")

    # Test with various parameters
    prompt = "what fruit is in the image"
    response = client.generate(
        prompt=prompt,
        images=[str(banana_image_path)],
        temperature=0.8,
        max_tokens=150,
        top_p=0.9,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )

    # Verify response is valid
    assert response is not None, "Response should not be None"
    assert len(response) > 0, "Response should not be empty"
    assert (
        "banana" in response.lower()
    ), f"Expected response to contain 'banana', but got: {response}"
