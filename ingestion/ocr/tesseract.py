"""Tesseract-based OCR provider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from PIL import Image

from ingestion.ocr import OCRProvider, OCRResult

logger = logging.getLogger(__name__)

_tesseract_warned = False


class TesseractOCRProvider(OCRProvider):
    """OCR provider using Tesseract via pytesseract."""

    def __init__(self, lang: str = "eng") -> None:
        """Initialize Tesseract OCR.

        Args:
            lang: Tesseract language code(s), e.g. 'eng' or 'eng+fra'.

        Raises:
            ImportError: if pytesseract or Pillow is not installed.
        """
        import pytesseract  # noqa: F401 — fail fast if not installed
        from PIL import Image as _Image  # noqa: F401

        self._lang = lang

    def extract_text(
        self,
        image: Union[str, bytes, Image.Image],
        source_location: Optional[str] = None,
    ) -> OCRResult:
        """Extract text from an image using Tesseract."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise ImportError(
                "pytesseract and Pillow are required for TesseractOCRProvider. "
                "Install with: pip install pytesseract pillow. "
                "Tesseract binary must be installed separately."
            ) from e

        if isinstance(image, str):
            pil_image = Image.open(image)
        elif isinstance(image, bytes):
            from io import BytesIO

            pil_image = Image.open(BytesIO(image))
        else:
            pil_image = image

        try:
            text = pytesseract.image_to_string(pil_image, lang=self._lang)
        except pytesseract.TesseractNotFoundError:
            global _tesseract_warned
            if not _tesseract_warned:
                logger.debug(
                    "Tesseract binary not found — skipping OCR for image files. "
                    "Install Tesseract to enable OCR: https://github.com/tesseract-ocr/tesseract"
                )
                _tesseract_warned = True
            return OCRResult(
                text="",
                confidence=0.0,
                source_location=source_location,
                extraction_method="ocr",
            )
        try:
            data = pytesseract.image_to_data(
                pil_image, lang=self._lang, output_type=pytesseract.Output.DICT
            )
        except Exception:
            data = {}

        confidence: Optional[float] = None
        confs = [int(c) for c in data.get("conf", []) if c != "-1"]
        if confs:
            confidence = sum(confs) / len(confs) / 100.0

        return OCRResult(
            text=text.strip(),
            confidence=confidence,
            source_location=source_location,
            extraction_method="ocr",
        )
