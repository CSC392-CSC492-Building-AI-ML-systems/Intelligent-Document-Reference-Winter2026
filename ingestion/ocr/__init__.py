"""OCR abstraction layer."""

from .base import OCRProvider, OCRResult
from .tesseract import TesseractOCRProvider

__all__ = ["OCRProvider", "OCRResult", "TesseractOCRProvider"]
