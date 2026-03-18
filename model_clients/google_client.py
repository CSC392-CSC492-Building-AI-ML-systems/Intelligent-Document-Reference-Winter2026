"""Google Gemini client for embeddings and inference via AI Studio."""

import logging
import os
from pathlib import Path
from typing import List, Optional, Union

from dotenv import load_dotenv

from model_clients.base import EmbeddingClient, InferenceClient

load_dotenv()
logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


class GoogleEmbeddingClient(EmbeddingClient):
    """Embedding client using Google's text-embedding model via genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "models/gemini-embedding-001",
    ):
        if genai is None:
            raise ImportError(
                "google-genai package is required. Install with: pip install google-genai"
            )
        self.api_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Google API key is required. Set GEMINI_API_KEY in .env or pass api_key."
            )
        self.client = genai.Client(api_key=self.api_key)
        self.model = model

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using the Gemini embedding model.

        Args:
            texts: Strings to embed.

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []

        # Google API allows at most 100 requests per batch
        max_batch_size = 100
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), max_batch_size):
            batch = texts[i : i + max_batch_size]
            result = self.client.models.embed_content(
                model=self.model,
                contents=batch,
            )
            all_embeddings.extend(e.values for e in result.embeddings)

        return all_embeddings


class GoogleInferenceClient(InferenceClient):
    """Inference client using Google Gemini generative models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash-lite",
    ):
        if genai is None:
            raise ImportError(
                "google-genai package is required. Install with: pip install google-genai"
            )
        self.api_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Google API key is required. Set GEMINI_API_KEY in .env or pass api_key."
            )
        self.client = genai.Client(api_key=self.api_key)
        self.model = model

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a text response from the Gemini model.

        Args:
            prompt: The full prompt string.
            **kwargs: Extra params (temperature, etc.).

        Returns:
            The generated text.
        """
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text

    def _downscale_image(
        self,
        data: bytes,
        max_size: int = 1024,
        jpeg_quality: int = 85,
    ) -> tuple[bytes, str]:
        """Downscale image to reduce tokens; returns (jpeg_bytes, 'image/jpeg')."""
        try:
            from io import BytesIO

            from PIL import Image

            img = Image.open(BytesIO(data)).convert("RGB")
            w, h = img.size
            if w <= max_size and h <= max_size:
                out = BytesIO()
                img.save(out, "JPEG", quality=jpeg_quality)
                return out.getvalue(), "image/jpeg"
            if w >= h:
                new_w = max_size
                new_h = int(h * max_size / w)
            else:
                new_h = max_size
                new_w = int(w * max_size / h)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, "JPEG", quality=jpeg_quality)
            return out.getvalue(), "image/jpeg"
        except Exception as e:
            logger.debug("Downscale skipped: %s", e)
            return data, "image/jpeg"

    def describe_image(
        self,
        image: Union[str, Path, bytes],
        prompt: Optional[str] = None,
        max_image_size: int = 1024,
    ) -> str:
        """Describe an image using the multimodal model (e.g. Gemini 2.5 Flash). Image in, text out.

        Images are downscaled (max side 1024px, JPEG 85%%) before sending to reduce tokens.

        Args:
            image: Path to image file or raw bytes.
            prompt: Optional prompt; default asks for a searchable description.
            max_image_size: Max width/height in pixels before downscale (default 1024).

        Returns:
            Text description of the image.
        """
        if types is None:
            raise ImportError("google-genai types required for describe_image")
        if isinstance(image, (str, Path)):
            path = Path(image)
            if not path.exists():
                raise FileNotFoundError(str(path))
            data = path.read_bytes()
        else:
            data = image
        data, mime_type = self._downscale_image(data, max_size=max_image_size)
        text_prompt = prompt or (
            "Describe this image in detail for search and retrieval. "
            "Include objects, colors, text if any, setting, and any other relevant details."
        )
        contents = [
            types.Part.from_text(text=text_prompt),
            types.Part.from_bytes(data=data, mime_type=mime_type),
        ]
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        return (response.text or "").strip()

    async def describe_image_async(
        self,
        image: Union[str, Path, bytes],
        prompt: Optional[str] = None,
    ) -> str:
        """Async version of describe_image. Runs describe_image in a thread to avoid blocking."""
        import asyncio

        return await asyncio.to_thread(self.describe_image, image, prompt)
