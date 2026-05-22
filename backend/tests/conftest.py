"""Shared pytest fixtures.

We force-set ``GROQ_API_KEY`` to a placeholder so ``Settings()`` is happy
during pure-Python tests that never actually hit the LLM (the agent
classes will instantiate ``ChatGroq`` lazily, and our tests mock them).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("GROQ_API_KEY", "test-key-placeholder")


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Clear the lru_cache around get_settings so per-test env tweaks apply."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
