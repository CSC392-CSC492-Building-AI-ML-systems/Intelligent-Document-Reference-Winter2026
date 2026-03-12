"""Configuration management."""

import os

import yaml

DEFAULT_CONFIG = {
    "max_workers": 4,
    "batch_size": 32,
    "timeout": 30,
    "log_level": "INFO",
}


def load_config(path: str = "config.yaml") -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return {**DEFAULT_CONFIG, **yaml.safe_load(f)}
    return DEFAULT_CONFIG.copy()
