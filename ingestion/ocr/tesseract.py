"""Tesseract-based OCR provider."""

from pathlib import Path
from typing import Optional, Union

from .base import OCRProvider, OCRResult


class TesseractOCRProvider(OCRProvider):
    """OCR provider using Tesseract via pytesseract."""

    def __init__(self, lang: str = "eng") -> None:
        """Initialize Tesseract OCR.

        Args:
            lang: Tesseract language code(s), e.g. 'eng' or 'eng+fra'.
        """
        self._lang = lang

    def extract_text(
        self,
        image: Union[str, bytes, "PIL.Image.Image"],
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

        text = pytesseract.image_to_string(pil_image, lang=self._lang)
        data = pytesseract.image_to_data(pil_image, lang=self._lang, output_type=pytesseract.Output.DICT)

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
