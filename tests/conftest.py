"""Shared test config: force the hermetic offline path BEFORE any app import.

All suites run deterministically — no API key, no network, no model downloads:
- ABA_OFFLINE_MODE=always   → rule router + extractive generation
- hashing embeddings        → deterministic vectors
- rerank disabled           → no cross-encoder download
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")
os.environ.setdefault("ABA_CACHE_FIRST", "false")
os.environ.setdefault("ABA_REFERENCE_DATE", "2026-06-08")  # seed-data anchor date

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def sample_engine():
    """One engine over the seed sample corpus (data/pdfs + business.db), shared by
    all suites that don't need uploads."""
    from app.config import get_settings
    from app.engine import Engine

    get_settings.cache_clear()
    return Engine()
