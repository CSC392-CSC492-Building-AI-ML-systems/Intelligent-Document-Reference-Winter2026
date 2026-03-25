"""OCR abstraction layer."""

from ingestion.ocr.base import OCRProvider, OCRResult
from ingestion.ocr.tesseract import TesseractOCRProvider

__all__ = ["OCRProvider", "OCRResult", "TesseractOCRProvider"]
