# Architecture

## Overview
The system follows a modular architecture with clear separation of concerns:

```
┌──────────┐     ┌──────────────┐     ┌───────────┐
│  Web UI  │────▶│   REST API   │────▶│  RAG Core │
└──────────┘     └──────────────┘     └───────────┘
                                             │
                      ┌───────────────────────┤
                      ▼                       ▼
                ┌──────────┐          ┌──────────────┐
                │ Embedder │          │   Retriever  │
                └──────────┘          └──────────────┘
                      │                       │
                      ▼                       ▼
                ┌──────────────────────────────────┐
                │          SQLite + Vec            │
                └──────────────────────────────────┘
```

## Key Design Decisions

### 1. SQLite over PostgreSQL
We chose SQLite with the `sqlite-vec` extension for vector search because:
- Zero operational overhead (no separate database server)
- Excellent read performance for our scale (< 1M documents)
- Easy backup and migration (single file)

### 2. Semantic Chunking
Documents are split using semantic boundaries (paragraphs, sections)
rather than fixed character counts. This preserves context and improves
retrieval relevance.

### 3. Hybrid Retrieval
We combine BM25 (keyword) and vector (semantic) search with reciprocal
rank fusion for better recall than either method alone.

## Module Responsibilities
| Module | Responsibility |
|--------|---------------|
| `ingestion/` | Document parsing, chunking, embedding |
| `inference/` | Query processing, retrieval, response generation |
| `embeddings/` | Embedding model abstraction |
| `db/` | Database operations and schema |
| `jobs/` | Background task processing |
| `watcher/` | File system change detection |
