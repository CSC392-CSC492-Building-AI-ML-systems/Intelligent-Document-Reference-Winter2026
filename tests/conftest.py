"""Pytest fixtures (basic)."""

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path
