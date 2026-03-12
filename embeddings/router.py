"""Get the configured embedding client."""

from config.settings import load_settings
from model_clients.registry import ClientRegistry


def get_embedding_client():
    settings = load_settings()
    return ClientRegistry.get_client("embedding", settings.default_embedding_backend)
