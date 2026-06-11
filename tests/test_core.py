"""Failing tests for core.py behavior changes (TDD RED — T1.3).

These tests are written BEFORE the corresponding implementation commits
(T1.4-T1.7). They will fail because:
- FetchError doesn't exist yet (T1.4)
- _get_with_retry still returns [] on failure (T1.5)
- fetch_range still sleeps unconditionally (T1.6)
- _normalize_item still uses `or` for numeric zero (T1.7)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
import requests
import requests_mock

import core


# ---------------------------------------------------------------------------
# Falsy-zero: _normalize_item
# ---------------------------------------------------------------------------

def test_normalize_preserves_zero_compra():
    """compra=0.0 must NOT fall through to buyPrice."""
    item = {"fecha": "2024-01-15", "compra": 0.0, "venta": 3.75}
    result = core._normalize_item(item)
    assert result is not None, "expected normalized row, got None"
    assert result["compra"] == 0.0
    assert result["venta"] == 3.75


def test_normalize_preserves_zero_venta():
    """venta=0.0 must NOT fall through to sellPrice."""
    item = {"fecha": "2024-01-15", "compra": 3.74, "venta": 0.0}
    result = core._normalize_item(item)
    assert result is not None
    assert result["venta"] == 0.0
    assert result["compra"] == 3.74


# ---------------------------------------------------------------------------
# Typed retry: _get_with_retry
# ---------------------------------------------------------------------------

def test_retry_network_raises(monkeypatch):
    """3 connection errors must raise FetchError(kind='network')."""
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, exc=requests.exceptions.ConnectionError)
        with pytest.raises(core.FetchError) as exc_info:
            core._get_with_retry({"date": "2024-01-15"}, max_retries=3)
        assert exc_info.value.kind == "network"


def test_retry_http_4xx_raises(monkeypatch):
    """HTTP 400 (non-retryable) must raise FetchError(kind='http_4xx')."""
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, status_code=400)
        with pytest.raises(core.FetchError) as exc_info:
            core._get_with_retry({"date": "2024-01-15"}, max_retries=3)
        assert exc_info.value.kind == "http_4xx"


def test_retry_http_5xx_raises_after_3_attempts(monkeypatch):
    """HTTP 503 x3 must raise FetchError(kind='http_5xx') after exhausting retries."""
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, status_code=503)
        with pytest.raises(core.FetchError) as exc_info:
            core._get_with_retry({"date": "2024-01-15"}, max_retries=3)
        assert exc_info.value.kind == "http_5xx"
        assert m.call_count == 3


def test_retry_parse_raises(monkeypatch):
    """Invalid JSON must raise FetchError(kind='parse')."""
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, text="not json {", status_code=200)
        with pytest.raises(core.FetchError) as exc_info:
            core._get_with_retry({"date": "2024-01-15"}, max_retries=3)
        assert exc_info.value.kind == "parse"


def test_retry_404_returns_empty(monkeypatch):
    """HTTP 404 is legitimately 'no data' — not an error. Returns []."""
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, status_code=404)
        result = core._get_with_retry({"date": "2099-01-15"}, max_retries=3)
        assert result == []


# ---------------------------------------------------------------------------
# Cache CRUD against tmp_path DB
# ---------------------------------------------------------------------------

def test_cache_put_and_get_roundtrip(tmp_cache_dir):
    """cache_put then cache_get returns the inserted row."""
    core.cache_put("2024-01-15", 3.74, 3.75, source="test")
    row = core.cache_get("2024-01-15")
    assert row is not None
    assert row["fecha"] == "2024-01-15"
    assert row["compra"] == 3.74
    assert row["venta"] == 3.75
    assert row["source"] == "test"


# ---------------------------------------------------------------------------
# Cache-hit short-circuit in fetch_range
# ---------------------------------------------------------------------------

def test_fetch_range_cache_hit_skips_sleep(monkeypatch, tmp_cache_dir):
    """When a month is fully cached, fetch_range must not call time.sleep."""
    # Pre-populate cache for January 2024 (20 days > MIN_DAYS_FOR_CACHED_MONTH=15)
    y, m = 2024, 1
    for d in range(1, 21):
        day_str = f"{y:04d}-{m:02d}-{d:02d}"
        core.cache_put(day_str, 3.7 + d * 0.001, 3.75 + d * 0.001)

    # Replace core.time with a tracking fake
    sleep_calls: list[float] = []
    fake_time = MagicMock()
    fake_time.sleep = lambda d: sleep_calls.append(d)
    monkeypatch.setattr(core, "time", fake_time)

    start = date(2024, 1, 1)
    end = date(2024, 1, 15)
    rows = core.fetch_range(start, end)

    assert len(rows) > 0, "expected cached rows for Jan 2024"
    assert sleep_calls == [], (
        f"fetch_range must skip time.sleep(0.3) on cache hit, got {sleep_calls}"
    )
