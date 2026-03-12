"""Manual end-to-end retrieval test.

Usage (from project root, with venv activated):
    uv run python scripts/test_retrieval_e2e.py

What it does:
    1. Creates a temporary SQLite DB with sqlite-vec.
    2. Inserts sample files, chunks, and embeddings.
    3. Runs a query through the full pipeline (Retriever → RAG → Citations).
    4. Prints the results so you can verify retrieval is working.

No external services (Ollama / OpenAI) are needed — it uses tiny fake
embeddings and a mock inference client so the flow can be validated locally.
"""

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.unified import UnifiedDatabase
from inference.responder import Responder

# ── Tiny helpers ─────────────────────────────────────────────────────────────

DIM = 3072  # must match schema.sql vec_items dimension


def _fake_embed(text: str) -> list[float]:
    """Deterministic pseudo-embedding: hash the text, expand to DIM floats."""
    h = hashlib.sha256(text.encode()).hexdigest()
    seed = [int(h[i : i + 2], 16) / 255.0 for i in range(0, min(len(h), DIM * 2), 2)]
    # Pad / tile to DIM
    vec = (seed * ((DIM // len(seed)) + 1))[:DIM]
    return vec


class FakeEmbeddingClient:
    """Returns deterministic embeddings so retrieval works without a real model."""

    def embed_text(self, texts: list[str]) -> list[list[float]]:
        return [_fake_embed(t) for t in texts]


class FakeInferenceClient:
    """Echoes context back so we can verify retrieval fed the right chunks."""

    def generate(self, prompt: str, **kw) -> str:
        # Extract the source lines from the prompt to prove chunks arrived
        sources = [
            line.strip()
            for line in prompt.splitlines()
            if line.strip().startswith("[SOURCE:")
        ]
        return (
            "Based on the retrieved context I can see:\n"
            + "\n".join(sources)
            + "\n(This is a fake LLM response for testing.)"
        )


# ── Sample data ──────────────────────────────────────────────────────────────

SAMPLE_FILES = [
    {
        "path": "/docs/python_guide.md",
        "chunks": [
            "Python is a high-level, interpreted programming language created by Guido van Rossum in 1991.",
            "Python supports multiple programming paradigms including procedural, object-oriented, and functional programming.",
            "The Python Package Index (PyPI) hosts over 400,000 packages for various tasks.",
        ],
    },
    {
        "path": "/docs/fastapi_intro.md",
        "chunks": [
            "FastAPI is a modern, fast web framework for building APIs with Python 3.7+ based on standard type hints.",
            "FastAPI uses Pydantic for data validation and Starlette for the web parts.",
            "FastAPI automatically generates OpenAPI (Swagger) documentation from your code.",
        ],
    },
    {
        "path": "/docs/sqlite_notes.md",
        "chunks": [
            "SQLite is a C-language library that implements a small, fast, self-contained SQL database engine.",
            "sqlite-vec is an extension that adds vector search capabilities to SQLite using virtual tables.",
        ],
    },
]


# ── Main ─────────────────────────────────────────────────────────────────────


async def main():
    embedder = FakeEmbeddingClient()

    # 1. Create a temp DB and seed it
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_retrieval.db")
        print(f"[1/4] Creating temp database: {db_path}")
        db = UnifiedDatabase(db_path=db_path)

        total_chunks = 0
        for file_info in SAMPLE_FILES:
            fpath = file_info["path"]
            fhash = hashlib.sha256(fpath.encode()).hexdigest()
            file_id = db.register_file(fpath, fhash, size=1000, modified=0.0)
            version_id = db.create_version(file_id, fhash)

            chunks = []
            embeddings = []
            for i, text in enumerate(file_info["chunks"]):
                chunks.append(
                    {
                        "chunk_id": f"{fpath}::chunk_{i}",
                        "chunk_index": i,
                        "start_offset": 0,
                        "end_offset": len(text),
                        "text_content": text,
                    }
                )
                embeddings.append(_fake_embed(text))

            db.add_document(file_id, version_id, chunks, embeddings)
            total_chunks += len(chunks)

        print(f"       Seeded {len(SAMPLE_FILES)} files, {total_chunks} chunks.\n")

        # 2. Run queries
        queries = [
            "Who created Python?",
            "What is FastAPI?",
            "How does sqlite vector search work?",
        ]

        responder = Responder(
            db=db,
            embedding_client=embedder,
            inference_client=FakeInferenceClient(),
        )

        for i, q in enumerate(queries, start=2):
            print(f'[{i}/4] Query: "{q}"')
            result = await responder.respond(q, top_k=3)

            print(f"       Answer: {result['answer'][:200]}")
            print(f"       Citations ({len(result['citations'])}):")
            for c in result["citations"]:
                print(f"         - {c['file_path']}  (relevance: {c['relevance']})")
            print(f"       Chunks returned: {len(result['chunks'])}")
            print()

        print("[Done] Retrieval pipeline is working end-to-end! ✓")


if __name__ == "__main__":
    asyncio.run(main())
