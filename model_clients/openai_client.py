"""OpenAI client for embeddings and vision language model inference."""

import base64
import os
from io import BytesIO
from typing import Any, Dict, List, Optional, Union

import PIL.Image
from dotenv import load_dotenv

from model_clients.base import EmbeddingClient, InferenceClient

# Load environment variables from .env file
load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class OpenAIEmbeddingClient(EmbeddingClient):
    """OpenAI client for text embeddings."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        dimensions: Optional[int] = None,
    ):
        """Initialize OpenAI embedding client.

        Args:
            api_key: OpenAI API key. If None, will load from OPENAI_API_KEY in .env file
                or environment variables.

        Raises:
            ImportError: If openai package is not installed.
            ValueError: If API key is not provided and OPENAI_API_KEY is not set.
        """
        if OpenAI is None:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            )

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY in .env file, "
                "environment variables, or pass api_key parameter."
            )

        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.dimensions = dimensions

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Embed text inputs.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        params: Dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }
        if self.dimensions is not None:
            params["dimensions"] = int(self.dimensions)

        response = self.client.embeddings.create(**params)
        return [item.embedding for item in response.data]


class OpenAIInferenceClient(InferenceClient):
    """OpenAI client for vision language model inference."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """Initialize OpenAI VLM inference client.

        Args:
            api_key: OpenAI API key. If None, will load from OPENAI_API_KEY in .env file
                or environment variables.
            model: Model name to use for inference. Defaults to "gpt-4o" which supports vision.

        Raises:
            ImportError: If openai package is not installed.
            ValueError: If API key is not provided and OPENAI_API_KEY is not set.
        """
        if OpenAI is None:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            )

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY in .env file, "
                "environment variables, or pass api_key parameter."
            )

        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def _encode_image(self, image: Union[str, PIL.Image.Image]) -> str:
        """Encode image to base64 string.

        Args:
            image: Image path (str) or PIL Image object.

        Returns:
            Base64 encoded image string.

        Raises:
            ValueError: If image type is unsupported.
        """
        if isinstance(image, str):
            pil_image = PIL.Image.open(image)
        elif isinstance(image, PIL.Image.Image):
            pil_image = image
        else:
            raise ValueError(f"Unsupported image type: {type(image)}")

        # Convert to RGB if necessary
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        # Encode to base64
        buffered = BytesIO()
        pil_image.save(buffered, format="JPEG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_base64

    def generate(
        self,
        prompt: str,
        images: Optional[List[Union[str, PIL.Image.Image]]] = None,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        **kwargs,
    ) -> str:
        """Generate text response from prompt and optional images.

        Args:
            prompt: Text prompt to send to the model.
            images: Optional list of image paths (str) or PIL Image objects.
            temperature: Sampling temperature between 0 and 2. Higher values make output
                more random. Defaults to 1.0.
            max_tokens: Maximum number of tokens to generate.
            top_p: Nucleus sampling parameter. Defaults to None.
            frequency_penalty: Frequency penalty between -2.0 and 2.0. Defaults to None.
            presence_penalty: Presence penalty between -2.0 and 2.0. Defaults to None.
            **kwargs: Additional parameters to pass to the API.

        Returns:
            Generated text response from the model.

        Raises:
            ValueError: If image type is unsupported or invalid parameters provided.
        """
        # Build messages
        messages = []

        # Build content list
        content = [{"type": "text", "text": prompt}]

        # Add images if provided
        if images:
            for image in images:
                img_base64 = self._encode_image(image)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
                    }
                )

        messages.append({"role": "user", "content": content})

        # Build API parameters
        api_params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            api_params["max_tokens"] = max_tokens
        if top_p is not None:
            api_params["top_p"] = top_p
        if frequency_penalty is not None:
            api_params["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            api_params["presence_penalty"] = presence_penalty

        # Add any additional kwargs
        api_params.update(kwargs)

        # Make API call
        response = self.client.chat.completions.create(**api_params)

        return response.choices[0].message.content
