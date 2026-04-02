"""Model-backed OCR provider kept under the historical Tesseract name.

This provider intentionally does not require the external Tesseract binary
or pytesseract Python package. Instead it attempts to use the runtime
inference client (if available) to perform image-to-text via model-based
vision capabilities (e.g., Ollama or other local VLMs). If no suitable
inference client is available, it returns an empty OCR result.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from PIL import Image as PILImage

from ingestion.ocr import OCRProvider, OCRResult

logger = logging.getLogger(__name__)


class TesseractOCRProvider(OCRProvider):
    """Model-backed OCR provider (keeps same class name for compatibility).

    The provider will try, at extraction time, to look up the application's
    runtime AppContext and use its `inference_client` to describe the image.
    This keeps the ingestion pipeline usable even when Tesseract is not
    installed, while preserving the public API expected by callers.
    """

    def __init__(self, lang: str = "eng") -> None:
        # lang kept for API compatibility but not used for model-based OCR.
        self._lang = lang

    def extract_text(
        self,
        image: Union[str, bytes, "PILImage"],
        source_location: Optional[str] = None,
    ) -> OCRResult:
        """Extract text from an image using a model-backed inference client.

        Attempts to obtain the global AppContext via backend.deps.get_context()
        and use its `inference_client.describe_image()` or
        `inference_client.generate()` methods when available. If no inference
        client is present or the client doesn't support image inputs, an empty
        OCRResult is returned (non-fatal).
        """
        # Import lazily to avoid hard dependency cycles at module import time.
        try:
            from backend.deps import get_context
        except Exception:
            # Not running inside the backend; cannot access inference client.
            logger.debug("Model-based OCR: backend context not available; skipping OCR")
            return OCRResult(
                text="",
                confidence=0.0,
                source_location=source_location,
                extraction_method="ocr",
            )

        try:
            ctx = get_context()
            client = getattr(ctx, "inference_client", None)
        except Exception:
            logger.debug("Model-based OCR: failed to obtain app context; skipping OCR")
            return OCRResult(
                text="",
                confidence=0.0,
                source_location=source_location,
                extraction_method="ocr",
            )

        if client is None:
            logger.debug(
                "Model-based OCR: no inference client configured; skipping OCR"
            )
            return OCRResult(
                text="",
                confidence=0.0,
                source_location=source_location,
                extraction_method="ocr",
            )

        # Prefer a describe_image method when available (Ollama client provides this).
        try:
            if hasattr(client, "describe_image"):
                # client.describe_image accepts path, bytes or PIL Image in our clients.
                text = client.describe_image(image)
                return OCRResult(
                    text=(text or "").strip(),
                    confidence=None,
                    source_location=source_location,
                    extraction_method="vlm",
                )

            # Fall back to a generic generate() that may accept image inputs (OpenAI client uses 'images' kw).
            if hasattr(client, "generate"):
                # Try calling generate with an images kw if supported.
                try:
                    text = client.generate(
                        "Describe the image and extract any visible text.",
                        images=[image],
                    )
                    return OCRResult(
                        text=(text or "").strip(),
                        confidence=None,
                        source_location=source_location,
                        extraction_method="vlm",
                    )
                except Exception:
                    # Not supported; continue to final fallback.
                    pass
        except Exception:
            logger.debug(
                "Model-based OCR: inference client failed to describe image",
                exc_info=True,
            )

        # If all else fails, return empty OCR result (non-fatal)
        return OCRResult(
            text="",
            confidence=0.0,
            source_location=source_location,
            extraction_method="ocr",
        )
