# Inference & Retrieval Pipeline

This directory contains the runtime query path for IntelligentDocRef:

```
User Query -> Retriever (hybrid search, selected-file scoped)
           -> RAGProcessor (prompt assembly)
           -> Inference client (LLM generation)
           -> Citation formatter (rank + confidence)
           -> API response
```

The core goal is **grounded answers over user-selected files only**, with clear citations and conservative confidence for weak matches.

## Key Modules

- `responder.py`
  - Orchestrates retrieval + generation.
  - Resolves `selected_files` to `file_ids` through DB metadata.
  - Handles empty retrieval fallback response.
  - Removes inline `(Source: ...)` style markers from model output (citations are shown in UI cards).

- `retriever.py`
  - Embeds query (`embedding_client.embed_text`) and retrieves candidates.
  - Performs dense vector retrieval (`search_with_metadata`) with hard scope to selected files.
  - Performs lexical retrieval (`search_text_with_metadata`) when available.
  - Fuses dense + lexical rankings using RRF and metadata boosts.
  - Returns top chunks with `hybrid_score` for citation scoring.

- `rag.py`
  - Builds the final prompt with retrieved context blocks.
  - Instructs model to output markdown and avoid inline source-path markers.
  - Executes synchronous client generation safely via `asyncio.to_thread`.

- `citation.py`
  - Deduplicates by file path and ranks strongest evidence per file.
  - Computes conservative `relevance_score` for UI display.
  - Down-weights noisy/low-evidence queries so random prompts do not appear highly matched.

- `router.py`
  - Returns the configured inference backend via `ClientRegistry`.

## End-to-End Request Flow

1. Frontend sends `POST /chat/query` with:
   - user message,
   - `selected_files`,
   - optional generation params.
2. `backend/api/routes_chat.py` creates `Responder`.
3. `Responder.respond(...)` converts selected paths to file IDs (exact file or directory-prefix expansion).
4. `Retriever.retrieve(...)` gets chunk candidates and ranks them.
5. `RAGProcessor.generate_response(...)` prompts the model.
6. `format_citations(...)` returns ranked source cards.
7. API responds with `{ answer, citations, processing_time_ms, ... }`.

## Retrieval Strategy (Current)

### 1) Hard file scope

- If user selected files/folders, retrieval is scoped to that subset only.
- If selection resolves to no indexed files, retrieval returns empty (no global fallback search).

### 2) Dense retrieval

- Query embedding is generated once.
- `db.unified.search_with_metadata` uses sqlite-vec cosine distance.

### 3) Lexical retrieval

- `db.unified.search_text_with_metadata` scores text/path matches via SQL `LIKE` heuristics.
- Useful for filename/path-anchored prompts and exact-term intent.

### 4) Hybrid rank fusion

- Reciprocal Rank Fusion (RRF) combines dense and lexical ranked lists.
- Metadata boost for file-target intent:
  - filename/stem mention in query,
  - extension mention (`.png`, `.md`, etc.),
  - token overlap with file stem,
  - single-selected-file boost.

### 5) Citation confidence calibration

- Citation confidence derives from:
  - semantic strength,
  - hybrid score,
  - lexical score,
  - path-intent match,
  - content term overlap.
- Weak/noisy evidence is penalized so unrelated queries do not show misleading high percentages.

## Selected Files Semantics

- `selected_files=None` -> normal global retrieval.
- `selected_files=[]` -> explicit "no files selected" behavior (returns no chunks).
- `selected_files=[...]` -> strict retrieval over matching file IDs only.

## Prompting Behavior

`RAGProcessor.build_prompt` currently enforces:

- answer must be grounded in provided context,
- markdown output preferred for UI rendering,
- no inline source path dump in answer body.

The UI renders sources separately from `citations` payload.

## Data Contracts

Retriever chunk item (typical):

```python
{
  "id": 123,
  "text_content": "...",
  "file_path": "/abs/path/file.md",
  "distance": 0.18,
  "lexical_score": 5,      # optional
  "hybrid_score": 0.094321 # added by retriever fusion
}
```

Citation item returned to UI:

```python
{
  "file_path": "/abs/path/file.md",
  "file_name": "file.md",
  "snippet": "chunk preview...",
  "relevance_score": 0.83,
  "chunk_index": 2
}
```

## Tuning Knobs

If you want to adjust behavior, start with:

- `Retriever.retrieve`: `fetch_k` over-fetch factor (`top_k * 4` currently).
- `Retriever._file_metadata_boost`: path-aware weighting.
- `citation.py`:
  - evidence weights,
  - noisy-query penalties,
  - confidence mapping (`_confidence_for_display`),
  - filtering threshold (`best * 0.80` floor).

## Testing

Run targeted retrieval tests:

```bash
uv run pytest tests/unit/test_retrieval_pipeline.py -v
uv run pytest tests/e2e/test_ingestion_retrieval_e2e.py -k "SelectedFileFiltering or EmptySelectionSemantics" -v
```

## Known Tradeoffs

- Path-aware boosts improve file targeting, but can over-bias if weighted too high.
- Conservative confidence protects demos from false certainty, but requires calibration for high-quality exact matches.
- SQL `LIKE` lexical path is simple and dependency-free; FTS5 remains an optional future upgrade.
