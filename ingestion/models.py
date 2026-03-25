"""Structured intermediate representation for the document ingestion pipeline.

All output from input parsers flows through these models. They are:
- Deterministic and serializable
- Stable across runs
- Directly consumable by the chunking engine
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class BlockType(str, Enum):
    """Semantic type of a content block."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE_BLOCK = "code_block"
    IMAGE_TEXT = "image_text"  # Text extracted from an image via OCR
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"
    UNKNOWN = "unknown"


class ExtractionMethod(str, Enum):
    """How the content was extracted."""

    NATIVE = "native"  # Direct extraction (e.g., PDF text layer)
    OCR = "ocr"  # Optical character recognition
    LLM_ASSISTED = "llm_assisted"  # Optional LLM cleanup/inference


class SourceModality(str, Enum):
    """Document modality / source type."""

    PDF = "pdf"
    IMAGE = "image"
    AUDIO = "audio"
    TEXT = "text"
    CODE = "code"


@dataclass
class FileMetadata:
    """File-level metadata for traceability (when source is a file)."""

    path: str  # Absolute or as-provided path
    relative_path: Optional[str] = None  # Relative to a chosen base (e.g. project root)
    filename: str = ""
    extension: str = ""
    size_bytes: Optional[int] = None
    mtime_iso: Optional[str] = None  # Last modified time, ISO format

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "mtime_iso": self.mtime_iso,
        }


# Lazy-loaded tiktoken encoder (cached, no API calls; encodings are local)
_tiktoken_encoder: Optional[Any] = None


def _get_encoder() -> Optional[Any]:
    """Return cached tiktoken encoder. Uses cl100k_base (GPT-4, GPT-3.5-turbo)."""
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            import tiktoken

            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            pass
    return _tiktoken_encoder


def estimate_tokens(text: str) -> int:
    """Token count for inference budgeting. Uses tiktoken (cl100k_base) when available; else ~4 chars/token fallback."""
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class BlockMetadata:
    """Metadata attached to a content block for chunk traceability and inference budgeting."""

    page_number: Optional[int] = None
    image_id: Optional[str] = None
    section_hierarchy: tuple[str, ...] = ()
    bbox: Optional[tuple[float, float, float, float]] = None  # x0, y0, x1, y1
    extraction_method: ExtractionMethod = ExtractionMethod.NATIVE
    content_length: Optional[int] = None  # character count
    token_estimate: Optional[int] = None  # rough tokens for inference budgeting


@dataclass
class ContentBlock:
    """A single content block in the structured document."""

    content: str
    block_type: BlockType
    source_modality: SourceModality
    metadata: BlockMetadata = field(default_factory=BlockMetadata)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for downstream consumption."""
        return {
            "content": self.content,
            "block_type": self.block_type.value,
            "source_modality": self.source_modality.value,
            "metadata": {
                "page_number": self.metadata.page_number,
                "image_id": self.metadata.image_id,
                "section_hierarchy": list(self.metadata.section_hierarchy),
                "bbox": self.metadata.bbox,
                "extraction_method": self.metadata.extraction_method.value,
                "content_length": self.metadata.content_length,
                "token_estimate": self.metadata.token_estimate,
            },
        }


@dataclass
class StructuredDocument:
    """Normalized intermediate representation produced by input parsers.

    Parsing, preprocessing, and chunking remain strictly separated.
    This model is the output of parsing and the input to preprocessing.
    """

    source_id: str  # File path or identifier
    blocks: list[ContentBlock] = field(default_factory=list)
    source_modality: SourceModality = SourceModality.TEXT
    file_metadata: Optional[FileMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for downstream consumption (dict structure for chunker/APIs)."""
        out: dict[str, Any] = {
            "source_id": self.source_id,
            "source_modality": self.source_modality.value,
            "blocks": [b.to_dict() for b in self.blocks],
        }
        if self.file_metadata is not None:
            out["file_metadata"] = self.file_metadata.to_dict()
        else:
            out["file_metadata"] = None
        return out


def file_metadata_from_path(
    path: Path, base_path: Optional[Path] = None
) -> FileMetadata:
    """Build FileMetadata from a file path. Uses stat for size/mtime."""
    try:
        stat = path.stat()
        size_bytes = stat.st_size
        mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        size_bytes = None
        mtime_iso = None
    relative_path = None
    if base_path and path.is_absolute() and base_path.is_absolute():
        try:
            relative_path = str(path.relative_to(base_path))
        except ValueError:
            pass
    return FileMetadata(
        path=str(path),
        relative_path=relative_path,
        filename=path.name,
        extension=path.suffix.lower(),
        size_bytes=size_bytes,
        mtime_iso=mtime_iso,
    )
