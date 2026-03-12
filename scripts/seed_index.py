"""Seed the database with sample documents for demo / testing.

Usage:
    uv run python scripts/seed_index.py
"""

import sys
from pathlib import Path

from config.settings import load_settings
from db.unified import UnifiedDatabase
from ingestion.pipeline import PipelineConfig, run
from model_clients.registry import ClientRegistry

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    settings = load_settings()
    db = UnifiedDatabase(db_path=settings.unified_db_path)

    print(f"Embedding backend: {settings.default_embedding_backend}")
    embedding_client = ClientRegistry.get_client(
        "embedding", settings.default_embedding_backend
    )
    embedder = embedding_client.embed_text  # List[str] -> List[List[float]]

    # Gather files to index
    sample_dir = ROOT / "ingestion" / "sample_files"
    extra_files = [
        ROOT / "README.md",
        ROOT / "SCAFFOLDING_NOTES.md",
    ]

    files_to_index: list[Path] = []
    for ext in ("*.txt", "*.md", "*.py"):
        files_to_index.extend(sample_dir.rglob(ext))
    for f in extra_files:
        if f.exists():
            files_to_index.append(f)

    if not files_to_index:
        print("No files found to index.")
        return

    print(f"Found {len(files_to_index)} files to index:")
    for f in files_to_index:
        print(f"  {f.relative_to(ROOT)}")

    config = PipelineConfig(
        embed_after_chunk=True,
        dedup_enabled=True,
        supported_extensions=(".txt", ".md", ".py", ".pdf"),
        use_structural_chunking=True,
        min_chunk_tokens=50,
        max_chunk_tokens=500,
        overlap_tokens=25,
    )

    from ingestion.crawler import DiscoveredFile

    for fpath in files_to_index:
        fpath = fpath.resolve()
        ext = fpath.suffix.lower()
        print(f"\nIndexing: {fpath.name} ...", end=" ", flush=True)
        try:
            st = fpath.stat()
            result = run(
                fpath.parent,
                config=config,
                db=db,
                embedder=embedder,
                files_override=[
                    DiscoveredFile(
                        path=fpath,
                        file_name=fpath.name,
                        extension=ext,
                        size_bytes=st.st_size,
                        modified_timestamp=st.st_mtime,
                    )
                ],
            )
            print(
                f"OK  ({result.final_chunk_count} chunks, {len(result.embeddings)} vectors)"
            )
        except Exception as e:
            print(f"FAILED: {e}")

    # Verify
    conn = db._get_conn()
    try:
        files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        print("\n--- Database totals ---")
        print(f"Files:  {files_count}")
        print(f"Chunks: {chunks_count}")
    finally:
        conn.close()

    # Mark files as indexed
    conn = db._get_conn()
    try:
        conn.execute("UPDATE files SET status = 'indexed' WHERE status != 'indexed'")
        conn.commit()
    finally:
        conn.close()

    print("\nDone! Database is seeded and ready for queries.")


if __name__ == "__main__":
    main()
