"""Main ingestion pipeline test suite.

Runs all tests for: parsing, preprocessing, semantic chunking, pipeline API,
and accuracy (content preserved, boilerplate filtered).

Run with: pytest tests/unit/test_ingestion_pipeline_main.py -v
"""

from tests.unit.test_ingestion import (
    test_chunk_document_produces_storeable_chunks,
    test_code_input_parses_file,
    test_get_input_handler_selects_by_extension,
    test_preprocessing_normalizes_whitespace,
    test_should_store_chunk_heuristic,
    test_structured_document_serializable,
    test_text_input_parses_file,
)
from tests.unit.test_pipeline import (
    test_ingest_chunks_have_required_schema,
    test_ingest_code_file_produces_code_chunks,
    test_ingest_filters_page_number_like_content,
    test_ingest_filters_short_boilerplate,
    test_ingest_preserves_substantive_content,
    test_ingest_result_to_dict_serializable,
    test_ingest_returns_valid_result_structure,
    test_ingest_sample_code_file,
    test_ingest_sample_text_file,
    test_ingest_text_file_produces_text_chunks,
    test_pipeline_instance_ingest,
    test_pipeline_modality_override,
    test_pipeline_respects_config,
)

__all__ = [
    # Parsing & preprocessing
    "test_text_input_parses_file",
    "test_code_input_parses_file",
    "test_get_input_handler_selects_by_extension",
    "test_preprocessing_normalizes_whitespace",
    "test_structured_document_serializable",
    # Semantic chunking
    "test_chunk_document_produces_storeable_chunks",
    "test_should_store_chunk_heuristic",
    # Pipeline & validity
    "test_ingest_returns_valid_result_structure",
    "test_ingest_chunks_have_required_schema",
    "test_ingest_result_to_dict_serializable",
    # Accuracy
    "test_ingest_text_file_produces_text_chunks",
    "test_ingest_code_file_produces_code_chunks",
    "test_ingest_filters_short_boilerplate",
    "test_ingest_filters_page_number_like_content",
    "test_ingest_preserves_substantive_content",
    # Pipeline config
    "test_pipeline_instance_ingest",
    "test_pipeline_respects_config",
    "test_pipeline_modality_override",
    # Sample files
    "test_ingest_sample_text_file",
    "test_ingest_sample_code_file",
]
