"""Shared pytest fixtures for sunat-tc-app tests.

The `tmp_cache_dir` fixture isolates cache.db and state.json into a per-test
tmp_path so tests can mutate the cache without touching the real
%APPDATA%/sunat-tc-app/ location.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Override core.CACHE_DB/STATE_FILE/CONFIG_FILE to fresh per-test paths.

    Yields a (cache_db, state_file) tuple for tests that want to assert on
    the resolved paths directly. The override is reverted when the test ends.
    Also clears SUNAT_TC_TOKEN so a token in the developer's environment
    never switches the tested fetch path from v1 to v2.
    """
    import core

    cache_db = tmp_path / "cache.db"
    state_file = tmp_path / "state.json"
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(core, "CACHE_DB", cache_db, raising=False)
    monkeypatch.setattr(core, "STATE_FILE", state_file, raising=False)
    monkeypatch.setattr(core, "CONFIG_FILE", config_file, raising=False)
    monkeypatch.delenv("SUNAT_TC_TOKEN", raising=False)
    return cache_db, state_file
