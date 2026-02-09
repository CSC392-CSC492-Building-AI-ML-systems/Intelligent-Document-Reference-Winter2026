"""Orchestrator: single entry point for parsing and preprocessing."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

from ingestion.models import StructuredDocument, file_metadata_from_path
from ingestion.parser import InputDocument, InputSource
from ingestion.preprocessing import preprocess


def parse_and_prepare(
    document: InputDocument,
    source: Union[str, Path, BinaryIO, InputSource],
    *,
    ocr_provider: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    config: Optional[Any] = None,
    base_path: Optional[Path] = None,
) -> StructuredDocument:
    """Parse and prepare a document for chunking. Attaches file_metadata when source is a file path."""
    parsed = document.parse(
        source=source,
        ocr_provider=ocr_provider,
        llm_client=llm_client,
        config=config,
    )
    preprocessed = preprocess(parsed)
    path = None
    if isinstance(source, (str, Path)):
        path = Path(source)
    elif hasattr(source, "path") and getattr(source, "path", None):
        path = Path(source.path)
    if path and path.exists() and path.is_file():
        preprocessed.file_metadata = file_metadata_from_path(path.resolve(), base_path)
    return preprocessed


def parse_and_prepare_batch(
    items: list[tuple[InputDocument, Union[str, Path, BinaryIO, InputSource]]],
    *,
    ocr_provider: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    config: Optional[Any] = None,
    max_workers: Optional[int] = None,
) -> list[StructuredDocument]:
    """Parse and prepare multiple documents concurrently.

    Uses ThreadPoolExecutor for I/O-bound parsing. Each document is
    parsed and preprocessed independently. Output order matches input order.

    Args:
        items: List of (InputDocument, source) pairs.
        ocr_provider: Optional OCR provider.
        llm_client: Optional LLM client.
        config: Optional IngestionConfig.
        max_workers: Max concurrent workers (default from config or 4).

    Returns:
        List of chunker-ready StructuredDocuments in input order.
    """
    if not items:
        return []

    workers = (
        max_workers
        if max_workers is not None
        else (getattr(config, "max_workers", None) or 4)
    )

    def process_one(idx: int, doc: InputDocument, src: Union[str, Path, BinaryIO, InputSource]) -> tuple[int, StructuredDocument]:
        result = parse_and_prepare(
            document=doc,
            source=src,
            ocr_provider=ocr_provider,
            llm_client=llm_client,
            config=config,
        )
        return (idx, result)

    results: dict[int, StructuredDocument] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(process_one, i, doc, src): i
            for i, (doc, src) in enumerate(items)
        }
        for future in as_completed(futures):
            idx, doc = future.result()
            results[idx] = doc

    return [results[i] for i in range(len(items))]
