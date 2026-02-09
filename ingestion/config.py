"""Ingestion pipeline configuration.

Concurrency, OCR, and LLM settings are bounded and configurable.
"""

from dataclasses import dataclass, field


@dataclass
class IngestionConfig:
    """Configuration for the document ingestion pipeline."""

    # Concurrency (I/O-bound only)
    max_workers: int = 4
    """Max concurrent workers for file/PDF page/OCR/LLM I/O."""

    # OCR
    ocr_enabled: bool = False
    """Enable OCR for images and scanned PDF pages. Requires OCR provider."""

    # LLM (opt-in, disabled by default)
    llm_enabled: bool = False
    """Enable optional LLM assistance for OCR cleanup / structural inference."""

    llm_ocr_cleanup: bool = False
    """Use LLM to clean/normalize OCR output. Requires llm_enabled."""

    llm_structural_inference: bool = False
    """Use LLM for weak structural inference when layout signals are insufficient."""

    # PDF block sizing (merge layout blocks into paragraph-sized chunks for semantic chunking)
    pdf_min_block_chars: int = 500
    """Minimum target size for a PDF block (~1 paragraph). Merge smaller blocks. 0 = no merging."""
    pdf_max_block_chars: int = 2500
    """Maximum size for a merged PDF block (~2-4 paragraphs). Keeps chunks embeddable."""
