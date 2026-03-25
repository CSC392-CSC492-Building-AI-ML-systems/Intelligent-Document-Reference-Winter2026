"""Google Gemini client for embeddings and inference via AI Studio."""

import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, List, Optional, Union

from dotenv import load_dotenv

from model_clients.base import EmbeddingClient, InferenceClient

load_dotenv()
logger = logging.getLogger(__name__)

_AUDIO_MIME_BY_EXTENSION: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".webm": "audio/webm",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}

_INLINE_AUDIO_MAX_MB = 20

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
        output_dimensionality: Optional[int] = None,
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
        self.output_dimensionality = output_dimensionality

    def _build_embed_kwargs(self, batch: List[str]) -> list[dict[str, Any]]:
        """Build compatible embed_content kwargs for different SDK versions."""
        base: dict[str, Any] = {
            "model": self.model,
            "contents": batch,
        }
        if self.output_dimensionality is None:
            return [base]

        dim = int(self.output_dimensionality)

        # Preferred path for modern SDKs.
        if types is not None and hasattr(types, "EmbedContentConfig"):
            try:
                typed_cfg = types.EmbedContentConfig(output_dimensionality=dim)
                return [{**base, "config": typed_cfg}]
            except Exception:
                # Fall through to dict-based variants for compatibility.
                pass

        # Compatibility variants observed across SDK revisions.
        return [
            {**base, "config": {"output_dimensionality": dim}},
            {**base, "config": {"outputDimensionality": dim}},
        ]

    def _normalize_dimension(self, vectors: List[List[float]]) -> List[List[float]]:
        """Ensure returned embeddings match requested dimensionality when provided."""
        if not vectors or self.output_dimensionality is None:
            return vectors

        target = int(self.output_dimensionality)
        out: List[List[float]] = []
        for idx, vec in enumerate(vectors):
            n = len(vec)
            if n == target:
                out.append(vec)
                continue
            if n > target:
                # Gemini embedding models are trained with MRL prefixes, so
                # truncating to a smaller requested dimension is valid.
                logger.debug(
                    "Truncating Gemini embedding vector from %d to %d at index %d",
                    n,
                    target,
                    idx,
                )
                out.append(vec[:target])
                continue
            raise ValueError(
                "Gemini returned fewer embedding dimensions than requested: "
                f"requested={target}, received={n}"
            )
        return out

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using the Gemini embedding model.

        Args:
            texts: Strings to embed.

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []

        # Google API allows at most 100 requests per batch.
        max_batch_size = 100
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), max_batch_size):
            batch = texts[i : i + max_batch_size]
            payloads = self._build_embed_kwargs(batch)

            last_error: Exception | None = None
            result = None
            for kwargs in payloads:
                try:
                    result = self.client.models.embed_content(**kwargs)
                    break
                except Exception as exc:
                    last_error = exc
                    continue

            if result is None:
                raise RuntimeError(
                    "Gemini embed_content failed for all config payload variants"
                ) from last_error

            batch_embeddings = [e.values for e in result.embeddings]
            all_embeddings.extend(self._normalize_dimension(batch_embeddings))

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

    @staticmethod
    def _is_retryable_unavailable_error(exc: Exception) -> bool:
        """Return True for transient Gemini capacity/rate errors that should be retried."""
        msg = str(exc).upper()
        retry_tokens = (
            "503",
            "UNAVAILABLE",
            "RESOURCE_EXHAUSTED",
            "TOO MANY REQUESTS",
            "429",
            "HIGH DEMAND",
        )
        return any(t in msg for t in retry_tokens)

    def _generate_content_with_retries(
        self,
        *,
        models: list[str],
        contents,
        retries_per_model: int = 3,
        initial_backoff_s: float = 1.0,
    ):
        """Try models in order with exponential backoff on transient availability errors."""
        last_exc: Optional[Exception] = None

        for model_name in models:
            backoff = initial_backoff_s
            for attempt in range(1, retries_per_model + 1):
                try:
                    return self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                    )
                except Exception as exc:
                    last_exc = exc
                    if not self._is_retryable_unavailable_error(exc):
                        raise

                    if attempt == retries_per_model:
                        logger.warning(
                            "Gemini model %s unavailable after %d attempts: %s",
                            model_name,
                            retries_per_model,
                            exc,
                        )
                        break

                    logger.warning(
                        "Gemini model %s unavailable (attempt %d/%d). Retrying in %.1fs: %s",
                        model_name,
                        attempt,
                        retries_per_model,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)
                    backoff *= 2

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Gemini content generation failed without an explicit error")

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a text response from the Gemini model.

        Args:
            prompt: The full prompt string.
            **kwargs: Extra params (temperature, etc.).

        Returns:
            The generated text.
        """
        model = kwargs.pop("model", self.model)
        response = self.client.models.generate_content(
            model=model,
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

    @staticmethod
    def _resolve_audio_mime_type(
        audio_path: Optional[Path],
        explicit_mime_type: Optional[str] = None,
    ) -> str:
        if explicit_mime_type:
            return explicit_mime_type

        if audio_path is not None:
            ext = audio_path.suffix.lower()
            if ext in _AUDIO_MIME_BY_EXTENSION:
                return _AUDIO_MIME_BY_EXTENSION[ext]
            guessed, _encoding = mimetypes.guess_type(str(audio_path))
            if guessed and guessed.startswith("audio/"):
                return guessed

        # Keep historical default for byte streams/unknown file extensions.
        return "audio/mpeg"

    @staticmethod
    def _file_state_name(file_obj: Any) -> str:
        """Best-effort extraction of a file processing state from SDK objects."""
        state = getattr(file_obj, "state", None)
        if state is None:
            return ""
        return str(getattr(state, "name", state)).upper()

    def _transcribe_large_audio_from_path(
        self,
        *,
        audio_path: Path,
        text_prompt: str,
        resolved_mime_type: str,
        models_to_try: list[str],
        retries_per_model: int,
    ):
        """Upload large audio files to Gemini Files API and transcribe via URI."""
        if types is None:
            raise ImportError("google-genai types required for transcribe_audio")
        files_api = getattr(self.client, "files", None)
        if files_api is None:
            raise RuntimeError(
                "Gemini client does not expose files API; cannot process large audio files"
            )

        upload_config = {"mime_type": resolved_mime_type}
        uploaded = files_api.upload(file=str(audio_path), config=upload_config)
        uploaded_name = getattr(uploaded, "name", None)

        try:
            # Wait briefly for file processing when the API returns PROCESSING.
            for _ in range(30):
                state_name = self._file_state_name(uploaded)
                if state_name in ("", "ACTIVE"):
                    break
                if state_name in ("FAILED", "ERROR"):
                    raise RuntimeError(
                        f"Gemini Files API failed while processing {audio_path.name}"
                    )
                if uploaded_name and hasattr(files_api, "get"):
                    uploaded = files_api.get(name=uploaded_name)
                time.sleep(2)

            file_part: Any = uploaded
            uri = getattr(uploaded, "uri", None)
            mime_type = getattr(uploaded, "mime_type", None) or resolved_mime_type
            if uri and hasattr(types.Part, "from_uri"):
                try:
                    file_part = types.Part.from_uri(uri=uri, mime_type=mime_type)
                except TypeError:
                    file_part = types.Part.from_uri(file_uri=uri, mime_type=mime_type)

            contents = [
                types.Part.from_text(text=text_prompt),
                file_part,
            ]

            return self._generate_content_with_retries(
                models=models_to_try,
                contents=contents,
                retries_per_model=max(1, retries_per_model),
            )
        finally:
            if uploaded_name and hasattr(files_api, "delete"):
                try:
                    files_api.delete(name=uploaded_name)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to delete uploaded Gemini file %s: %s",
                        uploaded_name,
                        cleanup_exc,
                    )

    def transcribe_audio(
        self,
        audio: Union[str, Path, bytes],
        prompt: Optional[str] = None,
        mime_type: Optional[str] = None,
        inline_audio_max_mb: int = _INLINE_AUDIO_MAX_MB,
        fallback_models: Optional[List[str]] = None,
        retries_per_model: int = 3,
    ) -> str:
        """Transcribe audio with Gemini multimodal input."""
        if types is None:
            raise ImportError("google-genai types required for transcribe_audio")

        audio_path: Optional[Path] = None
        if isinstance(audio, (str, Path)):
            audio_path = Path(audio)
            if not audio_path.exists():
                raise FileNotFoundError(str(audio_path))
            data = b""
        else:
            data = audio

        resolved_mime_type = self._resolve_audio_mime_type(
            audio_path=audio_path,
            explicit_mime_type=mime_type,
        )

        text_prompt = prompt or (
            "Transcribe this audio accurately. Return plain text only. "
            "If speakers are distinguishable, prefix lines with speaker labels."
        )
        models_to_try: list[str] = [self.model]
        if fallback_models is None:
            fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
        for m in fallback_models:
            if m and m not in models_to_try:
                models_to_try.append(m)

        if audio_path is not None:
            file_size_bytes = audio_path.stat().st_size
            inline_limit_bytes = max(1, int(inline_audio_max_mb)) * 1024 * 1024
            if file_size_bytes > inline_limit_bytes:
                response = self._transcribe_large_audio_from_path(
                    audio_path=audio_path,
                    text_prompt=text_prompt,
                    resolved_mime_type=resolved_mime_type,
                    models_to_try=models_to_try,
                    retries_per_model=retries_per_model,
                )
                return (response.text or "").strip()
            data = audio_path.read_bytes()

        contents = [
            types.Part.from_text(text=text_prompt),
            types.Part.from_bytes(data=data, mime_type=resolved_mime_type),
        ]

        response = self._generate_content_with_retries(
            models=models_to_try,
            contents=contents,
            retries_per_model=max(1, retries_per_model),
        )
        return (response.text or "").strip()
