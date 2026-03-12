"""Get the configured inference client."""

from config.settings import load_settings
from model_clients.registry import ClientRegistry


def get_inference_client():
    settings = load_settings()
    return ClientRegistry.get_client("inference", settings.default_inference_backend)
