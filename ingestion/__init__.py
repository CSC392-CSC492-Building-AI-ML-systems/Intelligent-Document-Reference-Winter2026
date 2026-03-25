"""Ingestion pipeline package.

Single directory for the complete pipeline: input (file/dir) → final selected chunks
→ optional embed & store. Semantic and structural chunking, density filter, crawler,
dedup, and embedding adapter live here.

Public entry points: run(input_path, ...) → IngestionOutput; ingest(source, ...) → IngestionResult.
"""

from ingestion.chunking import (
    StructuralChunk,
    chunk_document,
    should_store_chunk,
    structural_chunk_document,
)
from ingestion.config import IngestionConfig
from ingestion.crawler import DiscoveredFile, crawl_directory
from ingestion.models import (
    BlockMetadata,
    BlockType,
    ContentBlock,
    ExtractionMethod,
    FileMetadata,
    SourceModality,
    StructuredDocument,
    estimate_tokens,
    file_metadata_from_path,
)
from ingestion.ocr import OCRProvider, OCRResult, TesseractOCRProvider
from ingestion.orchestrator import parse_and_prepare, parse_and_prepare_batch
from ingestion.parser import (
    AudioInput,
    CodeInput,
    ImageInput,
    InputDocument,
    InputSource,
    PDFInput,
    TextInput,
    get_input_handler,
)
from ingestion.pipeline import (
    IngestionOutput,
    IngestionPipeline,
    IngestionResult,
    PipelineConfig,
    ingest,
    run,
    run_index,
)
from ingestion.preprocessing import preprocess

__all__ = [
    "parse_and_prepare",
    "parse_and_prepare_batch",
    "get_input_handler",
    "preprocess",
    "IngestionConfig",
    "InputDocument",
    "InputSource",
    "PDFInput",
    "ImageInput",
    "AudioInput",
    "TextInput",
    "CodeInput",
    "OCRProvider",
    "OCRResult",
    "TesseractOCRProvider",
    "StructuredDocument",
    "ContentBlock",
    "BlockMetadata",
    "FileMetadata",
    "BlockType",
    "ExtractionMethod",
    "SourceModality",
    "file_metadata_from_path",
    "estimate_tokens",
    "chunk_document",
    "should_store_chunk",
    "structural_chunk_document",
    "StructuralChunk",
    "IngestionPipeline",
    "IngestionResult",
    "IngestionOutput",
    "PipelineConfig",
    "ingest",
    "run",
    "run_index",
    "DiscoveredFile",
    "crawl_directory",
]
