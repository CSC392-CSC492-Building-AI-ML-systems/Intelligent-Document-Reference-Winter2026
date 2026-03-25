"""Runtime-configurable settings (stub).

TODO: load YAML / environment variables and expose a Settings object.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class Settings:
    unified_db_path: str = os.getenv("UNIFIED_DB_PATH", "local_search.db")
    watcher_db_path: str = os.getenv("WATCHER_DB_PATH", "file_registry.db")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    default_embedding_backend: str = os.getenv("DEFAULT_EMBEDDING_BACKEND", "gemini")
    default_inference_backend: str = os.getenv("DEFAULT_INFERENCE_BACKEND", "gemini")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "3072"))
    worker_poll_interval: float = float(os.getenv("WORKER_POLL_INTERVAL", "2.0"))
    ocr_enabled: bool = os.getenv("OCR_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    voyage_api_key: str = os.getenv("VOYAGE_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")


def load_settings() -> Settings:
    return Settings()
