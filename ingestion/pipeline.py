"""Ingestion pipeline: single entry point. Input (file/dir) → final chunks → optional embed & store.

Complete pipeline with clear input and output. All chunking (semantic + structural)
lives in ingestion; output is final selected chunks ready for vector DB.
"""

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, BinaryIO, Callable, List, Optional, Union

from ingestion.change_detector import ReindexStrategy
from ingestion.chunking import assert_contiguous, chunk_document
from ingestion.chunking.density_filter import filter_by_density
from ingestion.chunking.structural import structural_chunk_document
from ingestion.config import IngestionConfig
from ingestion.crawler import DiscoveredFile, crawl_directory
from ingestion.dedup import remove_near_duplicates_dicts
from ingestion.embedding_adapter import embed_texts_batched
from ingestion.models import BlockType, ContentBlock, FileMetadata, StructuredDocument
from ingestion.orchestrator import parse_and_prepare
from ingestion.parser import (
    AUDIO_FILE_EXTENSIONS,
    CODE_FILE_EXTENSIONS,
    IMAGE_FILE_EXTENSIONS,
    get_input_handler,
)
from ingestion.preprocessing import preprocess

logger = logging.getLogger(__name__)


def _record_file_ingestion_failure(
    db: Optional[Any],
    discovered: DiscoveredFile,
    _exc: BaseException,
) -> None:
    """Persist ``failed`` status so GET /files/ can show errors in the UI (red dot)."""
    if db is None or not hasattr(db, "mark_file_failed"):
        return
    try:
        resolved = str(Path(discovered.path).resolve())
        file_hash = (
            discovered.content_hash or hashlib.sha256(resolved.encode()).hexdigest()
        )
        db.mark_file_failed(
            resolved,
            file_hash,
            discovered.size_bytes,
            discovered.modified_timestamp,
        )
    except Exception:
        logger.warning(
            "Could not persist failed indexing status for %s",
            discovered.path,
            exc_info=True,
        )


# Lazy OCR provider: used when parsing images so text is extracted via Tesseract
# Set to False when load failed (so we only warn once)
_ocr_provider: Optional[Any] = None


def _get_ocr_provider() -> Optional[Any]:
    """Return a Tesseract OCR provider if OCR is enabled and available, else None."""
    if os.getenv("OCR_ENABLED", "false").lower() in ("false", "0", "no"):
        return None
    global _ocr_provider
    if _ocr_provider is not None:
        return _ocr_provider if _ocr_provider is not False else None
    try:
        from ingestion.ocr import TesseractOCRProvider

        _ocr_provider = TesseractOCRProvider()
        logger.info(
            "OCR (tesseract) loaded; image files (JPG, PNG, etc.) will be indexed."
        )
        return _ocr_provider
    except ImportError as e:
        _ocr_provider = False
        logger.warning(
            "OCR enabled but dependency missing (pytesseract/pillow not installed). "
            "Image OCR will be skipped; VLM will be used for images if available. %s",
            e,
        )
        return None
    except OSError as e:
        _ocr_provider = False
        logger.warning(
            "OCR enabled but tesseract binary not found. Image OCR will be skipped. %s",
            e,
        )
        return None


@dataclass
class IngestionResult:
    """Result for a single file: final selected chunks (and optional doc/metadata)."""

    source_id: str
    chunks: list[dict[str, Any]]
    document: StructuredDocument
    block_count: int = field(init=False)
    chunk_count: int = field(init=False)
    file_metadata: Optional[FileMetadata] = None

    def __post_init__(self) -> None:
        self.block_count = len(self.document.blocks)
        self.chunk_count = len(self.chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "block_count": self.block_count,
            "chunk_count": self.chunk_count,
            "chunks": self.chunks,
            "file_metadata": (
                self.file_metadata.to_dict() if self.file_metadata else None
            ),
        }


@dataclass
class IngestionOutput:
    """Output of the full ingestion pipeline (single file or directory).

    Final selected chunks (and optional embeddings) ready for vector DB.
    """

    chunks: List[dict[str, Any]]
    """Final selected chunks: chunk_id, chunk_index, start_offset, end_offset, text_content."""

    embeddings: List[List[float]] = field(default_factory=list)
    """Present if pipeline was run with embed_after_chunk=True and embedder."""

    files_processed: int = 0
    chunks_generated: int = 0
    chunks_after_dedup: int = 0

    @property
    def final_chunk_count(self) -> int:
        return len(self.chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunks": self.chunks,
            "embeddings": self.embeddings,
            "files_processed": self.files_processed,
            "chunks_generated": self.chunks_generated,
            "chunks_after_dedup": self.chunks_after_dedup,
            "final_chunk_count": self.final_chunk_count,
        }


@dataclass
class PipelineConfig:
    """Configuration for the complete ingestion pipeline (chunking, optional embed, store)."""

    ingestion: IngestionConfig = field(default_factory=IngestionConfig)

    # Semantic chunking (when use_structural_chunking=False)
    min_block_chars: int = 500
    max_block_chars: int = 2500
    min_chars_store: int = 30
    max_chars_store: int = 30_000
    min_tokens_store: int = 5
    max_tokens_store: int = 8000
    skip_boilerplate: bool = True
    store_block_types: Optional[tuple[BlockType, ...]] = None
    skip_block_types: tuple[BlockType, ...] = ()

    # Structural chunking (when use_structural_chunking=True)
    use_structural_chunking: bool = False
    min_chunk_tokens: int = 300
    max_chunk_tokens: int = 700
    overlap_tokens: int = 50
    max_overlap_ratio: float = 0.10
    remove_boilerplate: bool = False
    density_filter_enabled: bool = False
    min_tokens_density: int = 50
    min_content_word_ratio: float = 0.35

    # Crawler (when input is directory)
    # Must stay in sync with parser.CODE_FILE_EXTENSIONS + IMAGE_FILE_EXTENSIONS + AUDIO_FILE_EXTENSIONS (+ .pdf, .txt, .md, .rst)
    supported_extensions: tuple[str, ...] = (
        # Documents
        ".pdf",
        ".txt",
        ".md",
        ".rst",
        # Code / config
        ".py",
        ".js",
        ".mjs",
        ".cjs",
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
        ".html",
        ".css",
        ".scss",
        ".vue",
        ".svelte",
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        # Audio
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".oga",
        ".opus",
        ".webm",
        ".aiff",
        ".aif",
    )
    exclude_patterns: tuple[str, ...] = (
        "**/node_modules/**",
        "**/.git/**",
        "**/__pycache__/**",
        "**/*.pyc",
    )
    max_file_size_mb: float = 50.0

    # Post-chunk: embed, dedup, store
    embed_after_chunk: bool = False
    dedup_enabled: bool = False
    dedup_similarity_threshold: float = 0.95
    embedding_batch_size: int = 32

    # Parallelism
    max_workers: int = 4

    # Logging
    log_chunks_generated: bool = True
    log_final_vector_count: bool = True

    @classmethod
    def from_ingestion_config(cls, config: IngestionConfig) -> "PipelineConfig":
        return cls(
            ingestion=config,
            min_block_chars=config.pdf_min_block_chars,
            max_block_chars=config.pdf_max_block_chars,
        )


def _apply_boilerplate_to_document(document: StructuredDocument) -> StructuredDocument:
    from ingestion.boilerplate import remove_boilerplate

    new_blocks = []
    for b in document.blocks:
        cleaned = remove_boilerplate(b.content)
        if cleaned:
            new_blocks.append(
                ContentBlock(
                    content=cleaned,
                    block_type=b.block_type,
                    source_modality=b.source_modality,
                    metadata=b.metadata,
                )
            )
    return StructuredDocument(
        source_id=document.source_id,
        blocks=new_blocks,
        source_modality=document.source_modality,
        file_metadata=document.file_metadata,
    )


def _structural_chunk_and_filter(
    document: StructuredDocument,
    config: PipelineConfig,
) -> list[dict[str, Any]]:
    chunks = structural_chunk_document(
        document,
        min_tokens=config.min_chunk_tokens,
        max_tokens=config.max_chunk_tokens,
        overlap_tokens=config.overlap_tokens,
        max_overlap_ratio=config.max_overlap_ratio,
    )
    if config.density_filter_enabled:
        chunks = filter_by_density(
            chunks,
            min_tokens=config.min_tokens_density,
            min_content_word_ratio=config.min_content_word_ratio,
        )
    result = []
    for i, c in enumerate(chunks):
        entry: dict[str, Any] = {
            "chunk_id": c.chunk_id,
            "chunk_index": i,
            "start_offset": c.start_offset,
            "end_offset": c.end_offset,
            "text_content": c.text,
        }
        if c.page_number is not None:
            entry["page_number"] = c.page_number
        if c.section_hierarchy:
            entry["section"] = " > ".join(c.section_hierarchy)
        result.append(entry)
    return result


def _modality_for_ext(ext: str) -> str:
    if ext == ".pdf":
        return "pdf"
    if ext in (".txt", ".md", ".rst"):
        return "text"
    if ext in IMAGE_FILE_EXTENSIONS:
        return "image"
    if ext in AUDIO_FILE_EXTENSIONS:
        return "audio"
    if ext in CODE_FILE_EXTENSIONS:
        return "code"
    return "text"


def _register_and_mark_indexed(
    discovered: DiscoveredFile,
    db: Optional[Any],
) -> None:
    """Register a file in the DB and mark it indexed (no chunks to store).

    Called when a file was successfully parsed but produced no storable
    content (e.g. too short, empty after filtering).
    """
    if not db:
        return
    try:
        file_hash = (
            discovered.content_hash
            or hashlib.sha256(str(discovered.path).encode()).hexdigest()
        )
        file_id = db.register_file(
            str(discovered.path),
            file_hash,
            discovered.size_bytes,
            discovered.modified_timestamp,
        )
        db.mark_file_indexed(file_id)
    except Exception as exc:
        logger.warning(
            "Failed to mark %s as indexed (no chunks): %s", discovered.path, exc
        )


def _register_and_mark_failed(
    discovered: DiscoveredFile,
    db: Optional[Any],
    reason: str = "",
) -> None:
    """Register a file in the DB and mark it as failed.

    Called when embedding or storage failed so the UI shows the file
    needs attention rather than a false-positive green checkmark.
    """
    if not db:
        return
    try:
        file_hash = (
            discovered.content_hash
            or hashlib.sha256(str(discovered.path).encode()).hexdigest()
        )
        file_id = db.register_file(
            str(discovered.path),
            file_hash,
            discovered.size_bytes,
            discovered.modified_timestamp,
        )
        if hasattr(db, "mark_file_failed"):
            # Prefer the path-based failed-status API (used by the UI).
            db.mark_file_failed(
                str(discovered.path),
                file_hash,
                discovered.size_bytes,
                discovered.modified_timestamp,
            )
        else:
            # Backwards-compat fallback.
            db.mark_file_indexed(file_id)
    except Exception as exc:
        logger.warning(
            "Failed to mark %s as failed (%s): %s", discovered.path, reason, exc
        )


def _process_single_file(
    discovered: DiscoveredFile,
    cfg: PipelineConfig,
    root: Path,
    embedder: Optional[Callable[[List[str]], List[List[float]]]],
    llm_client: Optional[Any],
    db: Optional[Any],
) -> tuple[List[dict[str, Any]], List[List[float]], int]:
    """Process one file: parse → chunk → (embed → dedup → store).

    Returns:
        (chunks, embeddings, chunks_generated_count)
    """
    handler = get_input_handler(
        str(discovered.path), modality=_modality_for_ext(discovered.extension)
    )
    ocr_provider = _get_ocr_provider()
    parse_config = (
        replace(cfg.ingestion, ocr_enabled=True) if ocr_provider else cfg.ingestion
    )
    document = parse_and_prepare(
        handler,
        str(discovered.path),
        config=parse_config,
        base_path=root.parent if root.is_dir() else root.parent,
        ocr_provider=ocr_provider,
        llm_client=llm_client,
    )
    document = preprocess(document)

    from ingestion.models import BlockType, SourceModality

    is_image_doc = document.source_modality == SourceModality.IMAGE or any(
        b.block_type == BlockType.IMAGE_TEXT for b in document.blocks
    )
    min_chars_store = 1 if is_image_doc else cfg.min_chars_store
    min_tokens_store = 1 if is_image_doc else cfg.min_tokens_store
    skip_boilerplate = False if is_image_doc else cfg.skip_boilerplate

    if cfg.use_structural_chunking:
        if cfg.remove_boilerplate:
            document = _apply_boilerplate_to_document(document)
        chunks = _structural_chunk_and_filter(document, cfg)
    else:
        chunks = chunk_document(
            document,
            min_block_chars=cfg.min_block_chars,
            max_block_chars=cfg.max_block_chars,
            min_chars_store=min_chars_store,
            max_chars_store=cfg.max_chars_store,
            min_tokens_store=min_tokens_store,
            max_tokens_store=cfg.max_tokens_store,
            skip_boilerplate=skip_boilerplate,
            store_block_types=cfg.store_block_types,
            skip_block_types=cfg.skip_block_types,
        )

    file_chunks: List[dict[str, Any]] = []
    file_embs: List[List[float]] = []
    n_generated = len(chunks)

    if not chunks:
        _register_and_mark_indexed(discovered, db)
        return file_chunks, file_embs, n_generated

    if not cfg.embed_after_chunk:
        for c in chunks:
            rec = dict(c)
            rec["file_path"] = str(discovered.path)
            file_chunks.append(rec)
        return file_chunks, file_embs, n_generated

    texts = [c["text_content"] for c in chunks]
    try:
        max_embed_batch = 100
        embs: List[List[float]] = []
        for batch_start in range(0, len(texts), max_embed_batch):
            batch = texts[batch_start : batch_start + max_embed_batch]
            batch_embs = (
                embedder(batch)
                if embedder
                else embed_texts_batched(batch, batch_size=cfg.embedding_batch_size)
            )
            embs.extend(batch_embs)
            if len(texts) > max_embed_batch:
                logger.info(
                    "Embedded batch %d-%d of %d chunks for %s",
                    batch_start,
                    min(batch_start + max_embed_batch, len(texts)),
                    len(texts),
                    discovered.path.name,
                )
    except (RuntimeError, Exception) as e:
        logger.warning("Embedding failed for %s: %s", discovered.path, e)
        for c in chunks:
            rec = dict(c)
            rec["file_path"] = str(discovered.path)
            file_chunks.append(rec)
        _register_and_mark_failed(discovered, db, reason="embedding_failed")
        return file_chunks, file_embs, n_generated

    if len(embs) != len(chunks):
        logger.warning(
            "Embedding count mismatch for %s: %d chunks vs %d embeddings",
            discovered.path,
            len(chunks),
            len(embs),
        )
        for c in chunks:
            rec = dict(c)
            rec["file_path"] = str(discovered.path)
            file_chunks.append(rec)
        _register_and_mark_failed(discovered, db, reason="embedding_count_mismatch")
        return file_chunks, file_embs, n_generated

    if cfg.dedup_enabled:
        chunk_list = [
            {
                "chunk_id": c["chunk_id"],
                "chunk_index": i,
                "start_offset": c["start_offset"],
                "end_offset": c["end_offset"],
                "text_content": c["text_content"],
            }
            for i, c in enumerate(chunks)
        ]
        chunks, embs = remove_near_duplicates_dicts(
            chunk_list, embs, threshold=cfg.dedup_similarity_threshold
        )

    for c in chunks:
        rec = dict(c)
        rec["file_path"] = str(discovered.path)
        file_chunks.append(rec)
    file_embs = list(embs)

    if db and embs:
        file_hash = (
            discovered.content_hash
            or hashlib.sha256(str(discovered.path).encode()).hexdigest()
        )
        file_id = db.register_file(
            str(discovered.path),
            file_hash,
            discovered.size_bytes,
            discovered.modified_timestamp,
        )
        version_id = db.create_version(file_id, file_hash)
        if is_image_doc:
            logger.info(
                "Stored %d chunk(s) from image: %s",
                len(chunks),
                discovered.path,
            )
        store_chunks = [
            {
                "chunk_id": c["chunk_id"],
                "chunk_index": i,
                "start_offset": c["start_offset"],
                "end_offset": c["end_offset"],
                "text_content": c["text_content"],
            }
            for i, c in enumerate(chunks)
        ]
        try:
            assert_contiguous(store_chunks)
        except ValueError as ve:
            logger.warning(
                "Chunk contiguity check failed for %s: %s",
                discovered.path,
                ve,
            )
        try:
            db.add_document(file_id, version_id, store_chunks, embs)
        except ValueError as dim_err:
            if "dimension mismatch" in str(dim_err).lower():
                logger.warning(
                    "Dimension mismatch for %s — skipping. "
                    "Use Reindex in Settings to reconfigure the DB dimension. (%s)",
                    discovered.path,
                    dim_err,
                )
                _register_and_mark_failed(discovered, db, reason="dimension_mismatch")
                return file_chunks, file_embs, n_generated
            raise
        db.mark_file_indexed(file_id)
    elif embs and not db:
        logger.warning(
            "Chunks for %s were not stored (no database). Check backend context.",
            discovered.path,
        )

    return file_chunks, file_embs, n_generated


def run(
    input_path: Union[str, Path],
    *,
    config: Optional[PipelineConfig] = None,
    db: Optional[Any] = None,
    embedder: Optional[Callable[[List[str]], List[List[float]]]] = None,
    files_override: Optional[List[DiscoveredFile]] = None,
    llm_client: Optional[Any] = None,
) -> IngestionOutput:
    """Run the complete ingestion pipeline: input (file or directory) → final chunks → optional embed & store.

    Files are processed concurrently using a thread pool (``max_workers`` in
    ``PipelineConfig``).  DB writes are serialised via SQLite's internal locking.

    Args:
        input_path: File or directory path. If directory, crawls for supported_extensions.
        config: Pipeline config. Defaults if None.
        db: Optional UnifiedDatabase. If set and embeddings produced, stores chunks + vectors.
        embedder: Optional embedder when embed_after_chunk=True.
        files_override: If set, process only these discovered files (single-file or custom list).
        llm_client: Optional inference client with describe_image() for vision (image → text).

    Returns:
        IngestionOutput with final chunks and optional embeddings.
    """
    cfg = config or PipelineConfig()
    root = Path(input_path).resolve()

    if files_override is not None:
        file_iter = files_override
    elif root.is_file():
        ext = root.suffix.lower()
        if ext not in cfg.supported_extensions:
            return IngestionOutput(
                chunks=[], files_processed=0, chunks_generated=0, chunks_after_dedup=0
            )
        try:
            st = root.stat()
            file_iter = [
                DiscoveredFile(
                    path=root,
                    file_name=root.name,
                    extension=ext,
                    size_bytes=st.st_size,
                    modified_timestamp=st.st_mtime,
                )
            ]
        except OSError:
            return IngestionOutput(
                chunks=[], files_processed=0, chunks_generated=0, chunks_after_dedup=0
            )
    else:
        file_iter = list(
            crawl_directory(
                root,
                supported_extensions=cfg.supported_extensions,
                exclude_patterns=cfg.exclude_patterns,
                max_file_size_mb=cfg.max_file_size_mb,
            )
        )

    # One file in this run → re-raise after logging so job workers don't mark the job completed.
    single_file_run = len(file_iter) == 1

    all_chunks: List[dict[str, Any]] = []
    all_embeddings: List[List[float]] = []
    files_processed = 0
    chunks_generated = 0

    workers = min(cfg.max_workers, len(file_iter)) if file_iter else 1
    per_file_timeout = (
        120  # seconds — prevent any single file from hanging the pipeline
    )

    if workers <= 1:
        for discovered in file_iter:
            files_processed += 1
            try:
                logger.info(
                    "Indexing [%d/%d]: %s",
                    files_processed,
                    len(file_iter),
                    discovered.path.name,
                )
                fc, fe, ng = _process_single_file(
                    discovered, cfg, root, embedder, llm_client, db
                )
                all_chunks.extend(fc)
                all_embeddings.extend(fe)
                chunks_generated += ng
            except Exception as e:
                logger.exception("Failed to process %s: %s", discovered.path, e)
                _record_file_ingestion_failure(db, discovered, e)
                if single_file_run:
                    raise
                _register_and_mark_failed(discovered, db, reason=str(e)[:200])
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_file = {
                executor.submit(
                    _process_single_file,
                    discovered,
                    cfg,
                    root,
                    embedder,
                    llm_client,
                    db,
                ): discovered
                for discovered in file_iter
            }
            for future in as_completed(future_to_file):
                discovered = future_to_file[future]
                files_processed += 1
                try:
                    fc, fe, ng = future.result(timeout=per_file_timeout)
                    all_chunks.extend(fc)
                    all_embeddings.extend(fe)
                    chunks_generated += ng
                    logger.info(
                        "Indexed [%d/%d] %s (%d chunks)",
                        files_processed,
                        len(file_iter),
                        discovered.path.name,
                        ng,
                    )
                except TimeoutError:
                    logger.error(
                        "Timed out processing %s after %ds — skipping",
                        discovered.path,
                        per_file_timeout,
                    )
                    _register_and_mark_failed(discovered, db, reason="timeout")
                except Exception as e:
                    logger.exception("Failed to process %s: %s", discovered.path, e)
                    _record_file_ingestion_failure(db, discovered, e)
                    if single_file_run:
                        raise
                    _register_and_mark_failed(discovered, db, reason=str(e)[:200])

    if cfg.log_chunks_generated:
        logger.info("Chunks generated: %d", chunks_generated)
    if cfg.log_final_vector_count and all_embeddings:
        logger.info("Final vector count: %d", len(all_embeddings))

    return IngestionOutput(
        chunks=all_chunks,
        embeddings=all_embeddings,
        files_processed=files_processed,
        chunks_generated=chunks_generated,
        chunks_after_dedup=len(all_chunks),
    )


class IngestionPipeline:
    """Ingestion pipeline: single entry point for file/dir → final chunks."""

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()

    def ingest(
        self,
        source: Union[str, Path, BinaryIO],
        *,
        modality: Optional[str] = None,
        base_path: Optional[Path] = None,
        llm_client: Optional[Any] = None,
    ) -> IngestionResult:
        """Run pipeline on a single file/stream. Returns final selected chunks for that input."""
        handler = get_input_handler(source, modality=modality)
        ocr_provider = _get_ocr_provider()
        parse_config = (
            replace(self.config.ingestion, ocr_enabled=True)
            if ocr_provider
            else self.config.ingestion
        )
        document = parse_and_prepare(
            handler,
            source,
            config=parse_config,
            base_path=base_path,
            ocr_provider=ocr_provider,
            llm_client=llm_client,
        )

        if self.config.use_structural_chunking:
            if self.config.remove_boilerplate:
                document = _apply_boilerplate_to_document(document)
            chunks = _structural_chunk_and_filter(document, self.config)
        else:
            chunks = chunk_document(
                document,
                min_block_chars=self.config.min_block_chars,
                max_block_chars=self.config.max_block_chars,
                min_chars_store=self.config.min_chars_store,
                max_chars_store=self.config.max_chars_store,
                min_tokens_store=self.config.min_tokens_store,
                max_tokens_store=self.config.max_tokens_store,
                skip_boilerplate=self.config.skip_boilerplate,
                store_block_types=self.config.store_block_types,
                skip_block_types=self.config.skip_block_types,
            )

        return IngestionResult(
            source_id=document.source_id,
            chunks=chunks,
            document=document,
            file_metadata=document.file_metadata,
        )

    def run(
        self,
        input_path: Union[str, Path],
        *,
        db: Optional[Any] = None,
        embedder: Optional[Callable[[List[str]], List[List[float]]]] = None,
        files_override: Optional[List[DiscoveredFile]] = None,
    ) -> IngestionOutput:
        """Full pipeline: input (file or dir) → final chunks → optional embed & store."""
        return run(
            input_path,
            config=self.config,
            db=db,
            embedder=embedder,
            files_override=files_override,
        )


def run_index(path: str, strategy: Optional[ReindexStrategy] = None, ctx=None) -> None:
    """Index a file or directory. Uses ingestion pipeline (final chunks → embed → store)."""
    db = getattr(ctx, "db", None) or (getattr(ctx, "unified_db", None) if ctx else None)
    # Support both ctx.embedder (legacy) and ctx.embedding_client (AppContext)
    embedder_obj = getattr(ctx, "embedder", None) or getattr(
        ctx, "embedding_client", None
    )
    embedder = (
        embedder_obj.embed_text
        if embedder_obj and hasattr(embedder_obj, "embed_text")
        else None
    )
    llm_client = getattr(ctx, "inference_client", None)

    config = getattr(ctx, "pipeline_config", None) or PipelineConfig(
        embed_after_chunk=True, dedup_enabled=True
    )
    p = Path(path).resolve()
    if p.is_file():
        ext = p.suffix.lower()
        if ext not in config.supported_extensions:
            return

        if strategy == ReindexStrategy.SKIP:
            logger.info("Skipping indexing for %s: no changes detected", path)
            return
        elif strategy == ReindexStrategy.PURGE:
            # Remove from DB
            if db:
                db.remove_file(str(p))
            logger.info("Purged %s from index", path)
            return
        elif strategy == ReindexStrategy.METADATA_UPDATE:
            # Update only metadata
            if db:
                st = p.stat()
                db.update_file_metadata(str(p), st.st_mtime)
            logger.info("Updated metadata for %s", path)
            return
        # For FULL_INDEX, proceed with indexing
        try:
            st = p.stat()
            run(
                p.parent,
                config=config,
                db=db,
                embedder=embedder,
                llm_client=llm_client,
                files_override=[
                    DiscoveredFile(
                        path=p,
                        file_name=p.name,
                        extension=ext,
                        size_bytes=st.st_size,
                        modified_timestamp=st.st_mtime,
                    )
                ],
            )
        except Exception as e:
            logger.exception("Indexing failed for %s: %s", path, e)
    elif p.is_dir():
        run(p, config=config, db=db, embedder=embedder, llm_client=llm_client)
    else:
        # Path doesn't exist as file or dir, but check if it's in DB for purging
        if db and db.get_file_record(str(p)):
            db.remove_file(str(p))
            logger.info("Purged %s from index", path)


def ingest(
    source: Union[str, Path, BinaryIO],
    *,
    config: Optional[PipelineConfig] = None,
    modality: Optional[str] = None,
    base_path: Optional[Path] = None,
) -> IngestionResult:
    """Convenience: run pipeline on a single source; returns final selected chunks."""
    pipeline = IngestionPipeline(config=config)
    return pipeline.ingest(source, modality=modality, base_path=base_path)
