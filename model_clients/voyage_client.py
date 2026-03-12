"""Voyage AI embeddings client with multimodal support."""

import os
from typing import List, Optional, Union

import PIL.Image
from dotenv import load_dotenv

from config.settings import load_settings
from model_clients.base import EmbeddingClient

# Load environment variables from .env file
load_dotenv()

try:
    import voyageai
except ImportError:
    voyageai = None


class VoyageEmbeddingClient(EmbeddingClient):
    """Voyage AI client for text and image embeddings."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "voyage-multimodal-3.5"
    ):
        """Initialize Voyage client.

        Args:
            api_key: Voyage API key. If None, will load from VOYAGE_API_KEY in .env file
                or environment variables.
            model: Model name to use for embeddings.

        Raises:
            ImportError: If voyageai package is not installed.
            ValueError: If API key is not provided and VOYAGE_API_KEY is not set in .env
                or environment variables.
        """
        if voyageai is None:
            raise ImportError(
                "voyageai package is required. Install with: pip install voyageai"
            )

        self.api_key = api_key or os.getenv("VOYAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Voyage API key is required. Set VOYAGE_API_KEY in .env file, "
                "environment variables, or pass api_key parameter."
            )

        self.client = voyageai.Client(api_key=self.api_key)
        self.model = model
        settings = load_settings()
        self.embedding_dimension = settings.embedding_dimension

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Embed text inputs.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        inputs = [[text] for text in texts]
        result = self.client.multimodal_embed(inputs, model=self.model)
        return result.embeddings

    def embed_image(
        self, images: List[Union[str, PIL.Image.Image]]
    ) -> List[List[float]]:
        """Embed image inputs.

        Args:
            images: List of image paths (str) or PIL Image objects.

        Returns:
            List of embedding vectors.

        Raises:
            ValueError: If image type is unsupported.
        """
        if not images:
            return []

        # Convert paths to PIL Images if needed
        pil_images = []
        for img in images:
            if isinstance(img, str):
                pil_images.append(PIL.Image.open(img))
            elif isinstance(img, PIL.Image.Image):
                pil_images.append(img)
            else:
                raise ValueError(f"Unsupported image type: {type(img)}")

        # Format inputs: each image in its own list
        inputs = [[img] for img in pil_images]
        result = self.client.multimodal_embed(inputs, model=self.model)
        return result.embeddings

    def embed_multimodal(
        self,
        texts: Optional[List[str]] = None,
        images: Optional[List[Union[str, PIL.Image.Image]]] = None,
    ) -> List[List[float]]:
        """Embed mixed text and image inputs together.

        Args:
            texts: Optional list of text strings.
            images: Optional list of image paths or PIL Images.

        Returns:
            List of embedding vectors in the order of inputs.

        Raises:
            ValueError: If image type is unsupported.
        """
        inputs = []

        if texts:
            for text in texts:
                inputs.append([text])

        if images:
            for img in images:
                if isinstance(img, str):
                    pil_img = PIL.Image.open(img)
                elif isinstance(img, PIL.Image.Image):
                    pil_img = img
                else:
                    raise ValueError(f"Unsupported image type: {type(img)}")
                inputs.append([pil_img])

        if not inputs:
            return []

        result = self.client.multimodal_embed(inputs, model=self.model)
        return result.embeddings
