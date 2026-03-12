"""Ingestion pipeline configuration.

Concurrency, OCR, and LLM settings for parsing/preprocessing.
"""

from dataclasses import dataclass


@dataclass
class IngestionConfig:
    """Configuration for the document ingestion pipeline (parsing/preprocessing)."""

    max_workers: int = 4
    ocr_enabled: bool = False
    use_vision_for_images: bool = (
        True  # Use LLM (e.g. Gemini) to describe images when available
    )
    llm_enabled: bool = False
    llm_ocr_cleanup: bool = False
    llm_structural_inference: bool = False
    pdf_min_block_chars: int = 500
    pdf_max_block_chars: int = 2500
