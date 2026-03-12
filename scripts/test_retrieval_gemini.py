"""Live end-to-end retrieval test using the real Gemini API.

Usage (from project root, with venv activated):
    uv run python scripts/test_retrieval_gemini.py

What it does:
    1. Creates a temp SQLite DB (768-dim, matching Gemini text-embedding-004).
    2. Embeds sample chunks using the real Gemini embedding API.
    3. Stores them in the vector DB.
    4. Runs a query: embeds it, retrieves top-k, generates a Gemini answer.
    5. Prints everything so you can verify retrieval works end-to-end.

Requires:  GEMINI_API_KEY set in .env (or environment).
"""

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from db.unified import UnifiedDatabase
from inference.responder import Responder
from model_clients.google_client import GoogleEmbeddingClient, GoogleInferenceClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()
# ── Sample documents ─────────────────────────────────────────────────────────
SAMPLE_FILES = [
    {
        "path": "/docs/python_guide.md",
        "chunks": [
            "Python is a high-level, interpreted programming language created by Guido van Rossum and first released in 1991.",
            "Python supports multiple programming paradigms including procedural, object-oriented, and functional programming.",
            "The Python Package Index (PyPI) hosts over 400,000 packages for various tasks.",
        ],
    },
    {
        "path": "/docs/fastapi_intro.md",
        "chunks": [
            "FastAPI is a modern, fast web framework for building APIs with Python 3.7+ based on standard Python type hints.",
            "FastAPI automatically generates interactive OpenAPI documentation (Swagger UI) from your code.",
        ],
    },
    {
        "path": "/docs/sqlite_notes.md",
        "chunks": [
            "SQLite is a C-language library that implements a small, fast, self-contained, serverless SQL database engine.",
            "sqlite-vec is an extension that adds vector similarity search capabilities to SQLite using virtual tables.",
        ],
    },
]

# ── Main ─────────────────────────────────────────────────────────────────────


async def main():
    print("Initialising Gemini clients...")
    embedder = GoogleEmbeddingClient()
    llm = GoogleInferenceClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_gemini.db")
        db = UnifiedDatabase(db_path=db_path)

        # 1. Embed and store sample data
        print("\n[1/3] Embedding and storing sample documents...")
        total = 0
        for file_info in SAMPLE_FILES:
            fpath = file_info["path"]
            fhash = hashlib.sha256(fpath.encode()).hexdigest()
            file_id = db.register_file(fpath, fhash, size=1000, modified=0.0)
            version_id = db.create_version(file_id, fhash)

            texts = file_info["chunks"]
            embeddings = embedder.embed_text(texts)
            print(
                f"  Embedded {len(texts)} chunks from {fpath}  (dim={len(embeddings[0])})"
            )

            chunks = [
                {
                    "chunk_id": f"{fpath}::chunk_{i}",
                    "chunk_index": i,
                    "start_offset": 0,
                    "end_offset": len(t),
                    "text_content": t,
                }
                for i, t in enumerate(texts)
            ]
            db.add_document(file_id, version_id, chunks, embeddings)
            total += len(texts)

        print(f"  Total: {len(SAMPLE_FILES)} files, {total} chunks stored.\n")

        # 2. Run queries through the full pipeline
        queries = [
            "Who created the Python programming language?",
            "What is FastAPI and how does it generate documentation?",
            "How does vector search work in SQLite?",
        ]

        responder = Responder(db=db, embedding_client=embedder, inference_client=llm)

        for i, q in enumerate(queries, start=1):
            print(f'[{i+1}/3] Query: "{q}"')
            result = await responder.respond(q, top_k=3)

            print(f"  Answer: {result['answer'][:300]}")
            print(f"  Citations ({len(result['citations'])}):")
            for c in result["citations"]:
                print(f"    - {c['file_path']}  (relevance: {c['relevance']})")
            print()

        print("[Done] Live Gemini retrieval pipeline works end-to-end! ✓")


if __name__ == "__main__":
    asyncio.run(main())
