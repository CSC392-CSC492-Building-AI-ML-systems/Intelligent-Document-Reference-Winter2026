"""Single module: abstract input interface, all parsers (PDF, image, text, code), and router."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

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
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".kt",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".scala",
        ".r",
        ".sql",
        ".sh",
        ".bash",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".md",
        ".rst",
        ".html",
        ".css",
        ".scss",
        ".vue",
        ".svelte",
    }
)
_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
)


def get_input_handler(
    source: Union[str, Path, InputSource],
    modality: Optional[str] = None,
) -> InputDocument:
    """Return the appropriate InputDocument for the source."""
    if modality:
        modality = modality.lower()
        if modality == "pdf":
            return PDFInput()
        if modality == "image":
            return ImageInput()
        if modality == "code":
            return CodeInput()
        if modality == "text":
            return TextInput()
        return TextInput()
    path = (
        Path(source)
        if isinstance(source, (str, Path))
        else getattr(source, "path", None)
    )
    if path:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return PDFInput()
        if ext in _IMAGE_EXTENSIONS:
            return ImageInput()
        if ext in _CODE_EXTENSIONS:
            return CodeInput()
    return TextInput()


# --- Text ---


class TextInput(InputDocument):
    def parse(
        self,
        source: Union[str, Path, BinaryIO, InputSource],
        ocr_provider=None,
        llm_client=None,
        config=None,
    ) -> StructuredDocument:
        src = InputDocument._resolve_source(source)
        content = (
            src.path.read_text(encoding="utf-8", errors="replace")
            if src.path
            else (
                src.stream.read().decode("utf-8", errors="replace")
                if src.stream
                else ""
            )
        )
        block = ContentBlock(
            content=content.strip(),
            block_type=BlockType.PARAGRAPH,
            source_modality=SourceModality.TEXT,
            metadata=BlockMetadata(extraction_method=ExtractionMethod.NATIVE),
        )
        return StructuredDocument(
            source_id=src.identifier,
            blocks=[block] if block.content else [],
            source_modality=SourceModality.TEXT,
        )


# --- Code ---


class CodeInput(InputDocument):
    def parse(
        self,
        source: Union[str, Path, BinaryIO, InputSource],
        ocr_provider=None,
        llm_client=None,
        config=None,
    ) -> StructuredDocument:
        src = InputDocument._resolve_source(source)
        if src.path:
            content = src.path.read_text(encoding="utf-8", errors="replace")
            suffix = src.path.suffix.lower()
        else:
            content = (
                src.stream.read().decode("utf-8", errors="replace")
                if src.stream
                else ""
            )
            suffix = ""
        block = ContentBlock(
            content=content,
            block_type=BlockType.CODE_BLOCK,
            source_modality=SourceModality.CODE,
            metadata=BlockMetadata(
                extraction_method=ExtractionMethod.NATIVE,
                section_hierarchy=(suffix or "unknown",) if suffix else (),
            ),
        )
        return StructuredDocument(
            source_id=src.identifier,
            blocks=[block],
            source_modality=SourceModality.CODE,
        )


# --- Image ---


class ImageInput(InputDocument):
    def parse(
        self,
        source: Union[str, Path, BinaryIO, InputSource],
        ocr_provider=None,
        llm_client=None,
        config=None,
    ) -> StructuredDocument:
        src = InputDocument._resolve_source(source)
        blocks: list[ContentBlock] = []
        use_vision = config and getattr(config, "use_vision_for_images", True)
        has_describe = llm_client and getattr(llm_client, "describe_image", None)

        # Prefer LLM vision (e.g. Gemini 2.5 Flash) to describe image → text.
        # Descriptions are stored in vector DB chunks; when file changes, watcher
        # queues re-chunking so the vector DB stays up to date (no separate cache).
        if use_vision and has_describe and callable(has_describe):
            text = None
            path_str = str(src.path) if src.path else None
            image_input: Union[str, bytes] = (
                path_str if path_str else (src.stream.read() if src.stream else b"")
            )
            if hasattr(src.stream, "seek"):
                src.stream.seek(0)
            try:
                text = llm_client.describe_image(image_input)
            except Exception as e:
                logger.warning(
                    "Vision LLM describe_image failed for %s: %s",
                    src.identifier,
                    e,
                )
                text = None
            if not (text or "").strip():
                try:
                    if hasattr(src.stream, "seek"):
                        src.stream.seek(0)
                    text = llm_client.describe_image(
                        image_input,
                        prompt="What is in this image? Reply in one short sentence for document search.",
                    )
                except Exception as e:
                    logger.debug(
                        "VLM fallback describe failed for %s: %s", src.identifier, e
                    )
            if (text or "").strip():
                logger.debug("Vision LLM described image %s", src.identifier)
                blocks.append(
                    ContentBlock(
                        content=(text or "").strip(),
                        block_type=BlockType.IMAGE_TEXT,
                        source_modality=SourceModality.IMAGE,
                        metadata=BlockMetadata(
                            image_id=src.identifier,
                            extraction_method=ExtractionMethod.LLM_ASSISTED,
                        ),
                    )
                )
        # Fall back to OCR when vision LLM not used or failed
        if (
            not blocks
            and config
            and getattr(config, "ocr_enabled", False)
            and ocr_provider
        ):
            image_input = (
                str(src.path)
                if src.path
                else (src.stream.read() if src.stream else b"")
            )
            if hasattr(src.stream, "seek"):
                src.stream.seek(0)
            result = ocr_provider.extract_text(
                image_input, source_location=src.identifier
            )
            blocks.append(
                ContentBlock(
                    content=result.text,
                    block_type=BlockType.IMAGE_TEXT,
                    source_modality=SourceModality.IMAGE,
                    metadata=BlockMetadata(
                        image_id=src.identifier, extraction_method=ExtractionMethod.OCR
                    ),
                )
            )
        if not blocks:
            blocks.append(
                ContentBlock(
                    content="",
                    block_type=BlockType.IMAGE_TEXT,
                    source_modality=SourceModality.IMAGE,
                    metadata=BlockMetadata(
                        image_id=src.identifier,
                        extraction_method=ExtractionMethod.NATIVE,
                    ),
                )
            )
        return StructuredDocument(
            source_id=src.identifier,
            blocks=blocks,
            source_modality=SourceModality.IMAGE,
        )


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
            merged.append(
                ContentBlock(
                    content=content,
                    block_type=BlockType.PARAGRAPH,
                    source_modality=SourceModality.PDF,
                    metadata=BlockMetadata(
                        page_number=first_meta.page_number,
                        extraction_method=first_meta.extraction_method,
                        bbox=None,
                    ),
                )
            )
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


def _extract_blocks_from_page(
    page: Any, page_num: int
) -> tuple[int, list[ContentBlock]]:
    """Extract text and image blocks from a PDF page, sorted by reading order (y, x)."""
    blocks: list[ContentBlock] = []
    try:
        text_dict = page.get_text("dict", sort=True)
    except Exception:
        return (page_num, blocks)

    # --- text blocks ---
    for blk in text_dict.get("blocks", []):
        if blk.get("type", 0) == 1:
            # Image block reported by PyMuPDF "dict" mode – handled below
            continue
        lines = [
            "".join(s.get("text", "") for s in line.get("spans", []))
            for line in blk.get("lines", [])
        ]
        content = "\n".join(lines).strip()
        if not content:
            continue
        bbox = blk.get("bbox")
        blocks.append(
            ContentBlock(
                content=content,
                block_type=_pdf_block_type(blk),
                source_modality=SourceModality.PDF,
                metadata=BlockMetadata(
                    page_number=page_num,
                    bbox=tuple(bbox) if bbox and len(bbox) >= 4 else None,
                    extraction_method=ExtractionMethod.NATIVE,
                ),
            )
        )

    # --- embedded image blocks ---
    try:
        images = page.get_images(full=True)
    except Exception:
        images = []

    doc = page.parent
    for img_info in images:
        xref = img_info[0]
        try:
            img_rects = page.get_image_rects(xref)
            bbox_rect = img_rects[0] if img_rects else None
        except Exception:
            bbox_rect = None

        bbox_tuple = None
        if bbox_rect is not None:
            try:
                bbox_tuple = (
                    float(bbox_rect.x0),
                    float(bbox_rect.y0),
                    float(bbox_rect.x1),
                    float(bbox_rect.y1),
                )
            except Exception:
                pass

        # Extract raw image bytes
        try:
            img_data = doc.extract_image(xref)
            img_bytes = img_data.get("image", b"") if img_data else b""
        except Exception:
            img_bytes = b""

        if not img_bytes:
            continue

        # Store a placeholder block; actual OCR/VLM runs later in PDFInput.parse()
        blocks.append(
            ContentBlock(
                content="",  # filled in by OCR/VLM pass
                block_type=BlockType.IMAGE_TEXT,
                source_modality=SourceModality.PDF,
                metadata=BlockMetadata(
                    page_number=page_num,
                    bbox=bbox_tuple,
                    image_id=f"page{page_num}_xref{xref}",
                    extraction_method=ExtractionMethod.NATIVE,  # updated after OCR/VLM
                ),
            )
        )
        # Stash raw bytes on the block object so parse() can process them
        blocks[-1]._image_bytes = img_bytes  # type: ignore[attr-defined]

    # Sort all blocks by top-left position for reading order (y, then x)
    def _sort_key(b: ContentBlock) -> tuple[float, float]:
        bb = b.metadata.bbox
        if bb and len(bb) >= 4:
            return (bb[1], bb[0])
        return (0.0, 0.0)

    blocks.sort(key=_sort_key)
    return (page_num, blocks)


class PDFInput(InputDocument):
    def parse(
        self,
        source: Union[str, Path, BinaryIO, InputSource],
        ocr_provider=None,
        llm_client=None,
        config=None,
    ) -> StructuredDocument:
        try:
            import fitz
        except ImportError as e:
            raise ImportError(
                "PyMuPDF required for PDFInput. pip install pymupdf"
            ) from e
        src = InputDocument._resolve_source(source)
        ocr_enabled = config and getattr(config, "ocr_enabled", False)
        max_workers = getattr(config, "max_workers", 4) if config else 4
        use_vision = config and getattr(config, "use_vision_for_images", True)
        has_describe = llm_client and getattr(llm_client, "describe_image", None)
        doc = (
            fitz.open(str(src.path))
            if src.path
            else fitz.open(stream=src.stream.read(), filetype="pdf")
        )
        page_results: dict[int, list[ContentBlock]] = {}
        pages_to_ocr: list[tuple[int, bytes]] = []
        try:
            for i, page in enumerate(doc):
                page_num = i + 1
                _, block_list = _extract_blocks_from_page(page, page_num)
                native_len = sum(
                    len(b.content)
                    for b in block_list
                    if b.block_type != BlockType.IMAGE_TEXT
                )
                if ocr_enabled and ocr_provider and native_len < 50:
                    # Page has almost no native text — OCR the whole page
                    pix = page.get_pixmap(dpi=150)
                    pages_to_ocr.append((page_num, pix.tobytes("png")))
                    # Drop image placeholders for this page; the whole page is OCRed
                    page_results[page_num] = []
                else:
                    page_results[page_num] = block_list

            # --- Whole-page OCR for text-sparse pages ---
            if pages_to_ocr and ocr_provider:

                def ocr_one(item: tuple[int, bytes]) -> tuple[int, list[ContentBlock]]:
                    pnum, img_bytes = item
                    r = ocr_provider.extract_text(
                        img_bytes, source_location=f"page_{pnum}"
                    )
                    blks = (
                        [
                            ContentBlock(
                                content=r.text.strip(),
                                block_type=BlockType.IMAGE_TEXT,
                                source_modality=SourceModality.PDF,
                                metadata=BlockMetadata(
                                    page_number=pnum,
                                    extraction_method=ExtractionMethod.OCR,
                                ),
                            )
                        ]
                        if r.text.strip()
                        else []
                    )
                    return (pnum, blks)

                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    for fut in as_completed(
                        [ex.submit(ocr_one, x) for x in pages_to_ocr]
                    ):
                        pnum, blks = fut.result()
                        page_results[pnum] = blks

            # --- Embedded image OCR/VLM for pages with native text ---
            blocks: list[ContentBlock] = []
            for pnum in sorted(page_results.keys()):
                for blk in page_results[pnum]:
                    try:
                        img_bytes = getattr(blk, "_image_bytes", None)
                        if blk.block_type == BlockType.IMAGE_TEXT and img_bytes:
                            text = None
                            # Try VLM first (detailed description for search)
                            if use_vision and has_describe and callable(has_describe):
                                try:
                                    text = llm_client.describe_image(img_bytes)
                                except Exception as e:
                                    logger.debug(
                                        "VLM describe_image failed for %s: %s",
                                        blk.metadata.image_id,
                                        e,
                                    )
                            # Fall back to OCR
                            if not text and ocr_enabled and ocr_provider:
                                try:
                                    r = ocr_provider.extract_text(
                                        img_bytes,
                                        source_location=blk.metadata.image_id,
                                    )
                                    text = r.text.strip() if r.text else None
                                except Exception as e:
                                    logger.debug(
                                        "OCR failed for %s: %s",
                                        blk.metadata.image_id,
                                        e,
                                    )
                            # If still no context, retry VLM with a simpler prompt (often gets a response when default returns empty)
                            if (
                                not (text or "").strip()
                                and use_vision
                                and has_describe
                                and callable(has_describe)
                            ):
                                try:
                                    fallback = llm_client.describe_image(
                                        img_bytes,
                                        prompt="What is in this image? Reply in one short sentence for document search.",
                                    )
                                    text = (fallback or "").strip()
                                except Exception as e:
                                    logger.debug(
                                        "VLM fallback describe failed for %s: %s",
                                        blk.metadata.image_id,
                                        e,
                                    )
                            method = (
                                ExtractionMethod.LLM_ASSISTED
                                if text and use_vision and has_describe
                                else (
                                    ExtractionMethod.OCR
                                    if text
                                    else ExtractionMethod.NATIVE
                                )
                            )
                            # Always chunk: use description/OCR text, or minimal placeholder only when all description attempts failed
                            content = (text or "").strip()
                            if not content:
                                pnum_val = blk.metadata.page_number or 0
                                content = f"[Embedded image on page {pnum_val}]"
                                logger.debug(
                                    "Embedded image %s: no description (VLM/OCR); using placeholder",
                                    blk.metadata.image_id,
                                )
                            else:
                                logger.info(
                                    "Embedded image %s described (%d chars)",
                                    blk.metadata.image_id,
                                    len(content),
                                )
                            blocks.append(
                                ContentBlock(
                                    content=content,
                                    block_type=BlockType.IMAGE_TEXT,
                                    source_modality=SourceModality.PDF,
                                    metadata=BlockMetadata(
                                        page_number=blk.metadata.page_number,
                                        bbox=blk.metadata.bbox,
                                        image_id=blk.metadata.image_id,
                                        extraction_method=method,
                                    ),
                                )
                            )
                        else:
                            if blk.content:
                                blocks.append(blk)
                    except Exception as e:
                        logger.warning(
                            "Skipping block (page %s) due to error: %s",
                            pnum,
                            e,
                            exc_info=False,
                        )
                        if blk.block_type != BlockType.IMAGE_TEXT and blk.content:
                            blocks.append(blk)

            min_chars = getattr(config, "pdf_min_block_chars", 500) if config else 500
            max_chars = getattr(config, "pdf_max_block_chars", 2500) if config else 2500
            blocks = _merge_small_pdf_blocks(blocks, min_chars, max_chars)
        finally:
            doc.close()
        return StructuredDocument(
            source_id=src.identifier, blocks=blocks, source_modality=SourceModality.PDF
        )
