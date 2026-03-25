"""OCR abstraction layer."""

from ingestion.ocr.base import OCRProvider, OCRResult

__all__ = ["OCRProvider", "OCRResult", "TesseractOCRProvider"]


def __getattr__(name):
    if name == "TesseractOCRProvider":
        from ingestion.ocr.tesseract import TesseractOCRProvider

        return TesseractOCRProvider
    raise AttributeError(name)
