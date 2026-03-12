"""Preprocessing layer for chunker-ready output.

Cleans OCR and extraction artifacts, normalizes whitespace and encoding,
linearizes structured blocks without losing hierarchy.
Parsing, preprocessing, and chunking remain strictly separated.
"""

import re
import unicodedata

from ingestion.models import (
    BlockMetadata,
    ContentBlock,
    ExtractionMethod,
    StructuredDocument,
    estimate_tokens,
)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace: collapse runs, strip lines, normalize unicode."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_ocr_artifacts(text: str) -> str:
    """Remove common OCR artifacts (hyphenation at line breaks, etc.)."""
    if not text:
        return ""
    # Fix hyphenation at line breaks: "word-\nnext" -> "word\nnext"
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    # Remove stray control characters
    text = "".join(
        c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\r\t"
    )
    return text


def _clean_block(block: ContentBlock) -> ContentBlock:
    """Clean a single block: normalize whitespace and optionally OCR artifacts."""
    content = block.content
    if block.metadata.extraction_method == ExtractionMethod.OCR:
        content = _clean_ocr_artifacts(content)
    content = _normalize_whitespace(content)
    meta = block.metadata
    new_meta = BlockMetadata(
        page_number=meta.page_number,
        image_id=meta.image_id,
        section_hierarchy=meta.section_hierarchy,
        bbox=meta.bbox,
        extraction_method=meta.extraction_method,
        content_length=len(content),
        token_estimate=estimate_tokens(content),
    )
    return ContentBlock(
        content=content,
        block_type=block.block_type,
        source_modality=block.source_modality,
        metadata=new_meta,
    )


def preprocess(document: StructuredDocument) -> StructuredDocument:
    """Preprocess a structured document for chunking.

    - Cleans OCR and extraction artifacts
    - Normalizes whitespace and encoding
    - Linearizes blocks preserving metadata for chunk traceability
    - Filters empty blocks (after cleaning)

    Args:
        document: Output from an InputDocument.parse().

    Returns:
        Chunker-ready StructuredDocument with preserved metadata.
    """
    cleaned_blocks: list[ContentBlock] = []
    for block in document.blocks:
        cleaned = _clean_block(block)
        if cleaned.content:
            cleaned_blocks.append(cleaned)

    return StructuredDocument(
        source_id=document.source_id,
        blocks=cleaned_blocks,
        source_modality=document.source_modality,
        file_metadata=document.file_metadata,
    )
