# Frequently Asked Questions

## General

**Q: What file formats are supported?**
A: PDF, DOCX, TXT, MD, HTML, images (with OCR), and source code files.

**Q: How large can documents be?**
A: There's no hard limit, but documents over 100MB may cause memory
issues. We recommend splitting very large files.

**Q: Can I use my own embedding model?**
A: Yes! Implement the `EmbeddingProvider` interface and register
it in `embeddings/router.py`.

## Technical

**Q: How does semantic chunking work?**
A: We use a combination of structural markers (headings, paragraphs)
and embedding similarity to find natural break points in documents.
Chunks aim for ~512 tokens with 64-token overlap.

**Q: What vector search algorithm is used?**
A: We use HNSW (Hierarchical Navigable Small World) via the
sqlite-vec extension, with cosine similarity as the distance metric.

**Q: How are citations generated?**
A: The system tracks which chunks were used to answer each query
and maps them back to source documents with page numbers when available.

## Operations

**Q: How do I back up the index?**
A: Simply copy the SQLite database file. For zero-downtime backups,
use the `.backup` SQLite command.

**Q: Can I run this without an internet connection?**
A: Yes, if you use a local embedding model (e.g., via Ollama).
The LLM for response generation can also be run locally.
