"""Single module: abstract input interface, all parsers (PDF, image, text, code), and router."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

from ingestion.models import (
    BlockMetadata,
    BlockType,
    ContentBlock,
    ExtractionMethod,
    SourceModality,
    StructuredDocument,
)

# --- Source & base ---


@dataclass
class InputSource:
    """Source of input: file path or binary stream."""

    path: Optional[Path] = None
    stream: Optional[BinaryIO] = None
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.path is None and self.stream is None:
            raise ValueError("Either path or stream must be provided")
        if not self.identifier and self.path:
            self.identifier = str(self.path)


class InputDocument(ABC):
    """Abstract base for document input handlers."""

    @abstractmethod
    def parse(
        self,
        source: Union[str, Path, BinaryIO, InputSource],
        ocr_provider: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> StructuredDocument:
        raise NotImplementedError

    @staticmethod
    def _resolve_source(source: Union[str, Path, BinaryIO, InputSource]) -> InputSource:
        if isinstance(source, InputSource):
            return source
        if isinstance(source, (str, Path)):
            return InputSource(path=Path(source))
        if hasattr(source, "read") and callable(getattr(source, "read")):
            return InputSource(stream=source, identifier="<stream>")
        raise TypeError(f"Unsupported source type: {type(source)}")


# --- Router ---

_CODE_EXTENSIONS = frozenset(
    {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".rb", ".php",
     ".swift", ".c", ".cpp", ".h", ".hpp", ".cs", ".scala", ".r", ".sql", ".sh", ".bash",
     ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".md", ".rst", ".html", ".css",
     ".scss", ".vue", ".svelte"}
)
_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"})


def get_input_handler(
    source: Union[str, Path, InputSource],
    modality: Optional[str] = None,
) -> InputDocument:
    """Return the appropriate InputDocument for the source."""
    if modality:
        modality = modality.lower()
        if modality == "pdf": return PDFInput()
        if modality == "image": return ImageInput()
        if modality == "code": return CodeInput()
        if modality == "text": return TextInput()
        return TextInput()
    path = Path(source) if isinstance(source, (str, Path)) else getattr(source, "path", None)
    if path:
        ext = path.suffix.lower()
        if ext == ".pdf": return PDFInput()
        if ext in _IMAGE_EXTENSIONS: return ImageInput()
        if ext in _CODE_EXTENSIONS: return CodeInput()
    return TextInput()


# --- Text ---


class TextInput(InputDocument):
    def parse(self, source: Union[str, Path, BinaryIO, InputSource], ocr_provider=None, llm_client=None, config=None) -> StructuredDocument:
        src = InputDocument._resolve_source(source)
        content = src.path.read_text(encoding="utf-8", errors="replace") if src.path else (src.stream.read().decode("utf-8", errors="replace") if src.stream else "")
        block = ContentBlock(
            content=content.strip(),
            block_type=BlockType.PARAGRAPH,
            source_modality=SourceModality.TEXT,
            metadata=BlockMetadata(extraction_method=ExtractionMethod.NATIVE),
        )
        return StructuredDocument(source_id=src.identifier, blocks=[block] if block.content else [], source_modality=SourceModality.TEXT)


# --- Code ---


class CodeInput(InputDocument):
    def parse(self, source: Union[str, Path, BinaryIO, InputSource], ocr_provider=None, llm_client=None, config=None) -> StructuredDocument:
        src = InputDocument._resolve_source(source)
        if src.path:
            content = src.path.read_text(encoding="utf-8", errors="replace")
            suffix = src.path.suffix.lower()
        else:
            content = src.stream.read().decode("utf-8", errors="replace") if src.stream else ""
            suffix = ""
        block = ContentBlock(
            content=content,
            block_type=BlockType.CODE_BLOCK,
            source_modality=SourceModality.CODE,
            metadata=BlockMetadata(extraction_method=ExtractionMethod.NATIVE, section_hierarchy=(suffix or "unknown",) if suffix else ()),
        )
        return StructuredDocument(source_id=src.identifier, blocks=[block], source_modality=SourceModality.CODE)


# --- Image ---


class ImageInput(InputDocument):
    def parse(self, source: Union[str, Path, BinaryIO, InputSource], ocr_provider=None, llm_client=None, config=None) -> StructuredDocument:
        src = InputDocument._resolve_source(source)
        blocks: list[ContentBlock] = []
        if config and getattr(config, "ocr_enabled", False) and ocr_provider:
            image_input: Union[str, bytes] = str(src.path) if src.path else (src.stream.read() if src.stream else b"")
            if hasattr(src.stream, "seek"): src.stream.seek(0)
            result = ocr_provider.extract_text(image_input, source_location=src.identifier)
            blocks.append(ContentBlock(content=result.text, block_type=BlockType.IMAGE_TEXT, source_modality=SourceModality.IMAGE,
                metadata=BlockMetadata(image_id=src.identifier, extraction_method=ExtractionMethod.OCR)))
        if not blocks:
            blocks.append(ContentBlock(content="", block_type=BlockType.IMAGE_TEXT, source_modality=SourceModality.IMAGE,
                metadata=BlockMetadata(image_id=src.identifier, extraction_method=ExtractionMethod.NATIVE)))
        return StructuredDocument(source_id=src.identifier, blocks=blocks, source_modality=SourceModality.IMAGE)


# --- PDF ---


def _merge_small_pdf_blocks(
    blocks: list[ContentBlock],
    min_chars: int,
    max_chars: int,
) -> list[ContentBlock]:
    """Merge consecutive PDF blocks so each is at least min_chars, and at most max_chars."""
    if not blocks or min_chars <= 0:
        return blocks
    merged: list[ContentBlock] = []
    acc_content: list[str] = []
    first_meta: Optional[BlockMetadata] = None

    def flush() -> None:
        nonlocal acc_content, first_meta
        if not acc_content or first_meta is None:
            return
        content = "\n\n".join(acc_content).strip()
        if content:
            merged.append(ContentBlock(
                content=content,
                block_type=BlockType.PARAGRAPH,
                source_modality=SourceModality.PDF,
                metadata=BlockMetadata(
                    page_number=first_meta.page_number,
                    extraction_method=first_meta.extraction_method,
                    bbox=None,
                ),
            ))
        acc_content = []
        first_meta = None

    for b in blocks:
        if not b.content.strip():
            continue
        cand = acc_content + [b.content]
        cand_len = len("\n\n".join(cand))
        if first_meta is None:
            first_meta = b.metadata
        if acc_content and cand_len > max_chars:
            flush()
            first_meta = b.metadata
            acc_content = [b.content]
        else:
            acc_content.append(b.content)
        if len("\n\n".join(acc_content)) >= min_chars:
            flush()
    flush()
    return merged


def _pdf_block_type(_blk: dict) -> BlockType:
    return BlockType.PARAGRAPH


def _extract_blocks_from_page(page: Any, page_num: int) -> tuple[int, list[ContentBlock]]:
    blocks: list[ContentBlock] = []
    try:
        text_dict = page.get_text("dict", sort=True)
    except Exception:
        return (page_num, blocks)
    for blk in text_dict.get("blocks", []):
        lines = ["".join(s.get("text", "") for s in line.get("spans", [])) for line in blk.get("lines", [])]
        content = "\n".join(lines).strip()
        if not content:
            continue
        bbox = blk.get("bbox")
        blocks.append(ContentBlock(
            content=content,
            block_type=_pdf_block_type(blk),
            source_modality=SourceModality.PDF,
            metadata=BlockMetadata(page_number=page_num, bbox=tuple(bbox) if bbox and len(bbox) >= 4 else None, extraction_method=ExtractionMethod.NATIVE),
        ))
    return (page_num, blocks)


class PDFInput(InputDocument):
    def parse(self, source: Union[str, Path, BinaryIO, InputSource], ocr_provider=None, llm_client=None, config=None) -> StructuredDocument:
        try:
            import fitz
        except ImportError as e:
            raise ImportError("PyMuPDF required for PDFInput. pip install pymupdf") from e
        src = InputDocument._resolve_source(source)
        ocr_enabled = config and getattr(config, "ocr_enabled", False)
        max_workers = getattr(config, "max_workers", 4) if config else 4
        doc = fitz.open(str(src.path)) if src.path else fitz.open(stream=src.stream.read(), filetype="pdf")
        page_results: dict[int, list[ContentBlock]] = {}
        pages_to_ocr: list[tuple[int, bytes]] = []
        try:
            for i, page in enumerate(doc):
                page_num = i + 1
                _, block_list = _extract_blocks_from_page(page, page_num)
                native_len = sum(len(b.content) for b in block_list)
                if ocr_enabled and ocr_provider and native_len < 50:
                    pix = page.get_pixmap(dpi=150)
                    pages_to_ocr.append((page_num, pix.tobytes("png")))
                    page_results[page_num] = []
                else:
                    page_results[page_num] = block_list
            if pages_to_ocr and ocr_provider:
                def ocr_one(item: tuple[int, bytes]) -> tuple[int, list[ContentBlock]]:
                    pnum, img_bytes = item
                    r = ocr_provider.extract_text(img_bytes, source_location=f"page_{pnum}")
                    blks = [ContentBlock(content=r.text.strip(), block_type=BlockType.IMAGE_TEXT, source_modality=SourceModality.PDF,
                        metadata=BlockMetadata(page_number=pnum, extraction_method=ExtractionMethod.OCR))] if r.text.strip() else []
                    return (pnum, blks)
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    for fut in as_completed([ex.submit(ocr_one, x) for x in pages_to_ocr]):
                        pnum, blks = fut.result()
                        page_results[pnum] = blks
            blocks = []
            for pnum in sorted(page_results.keys()):
                blocks.extend(page_results[pnum])
            min_chars = getattr(config, "pdf_min_block_chars", 500) if config else 500
            max_chars = getattr(config, "pdf_max_block_chars", 2500) if config else 2500
            blocks = _merge_small_pdf_blocks(blocks, min_chars, max_chars)
        finally:
            doc.close()
        return StructuredDocument(source_id=src.identifier, blocks=blocks, source_modality=SourceModality.PDF)
