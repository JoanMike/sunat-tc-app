"""Unit tests for core.validators (T1.8)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import validate_month, validate_range


# ---------------------------------------------------------------------------
# validate_range
# ---------------------------------------------------------------------------

def test_validate_range_valid_returns_tuple():
    today = date.today()
    start = today - timedelta(days=30)
    result = validate_range(start, today)
    assert result == (start, today)


def test_validate_range_end_after_today_returns_str():
    today = date.today()
    result = validate_range(today, today + timedelta(days=1))
    assert isinstance(result, str)
    assert "futura" in result.lower()


def test_validate_range_too_long_returns_str():
    today = date.today()
    start = today - timedelta(days=800)
    result = validate_range(start, today)
    assert isinstance(result, str)
    assert "730" in result or "rango" in result.lower()


def test_validate_range_start_after_end_returns_str():
    today = date.today()
    result = validate_range(today, today - timedelta(days=1))
    assert isinstance(result, str)
    assert "posterior" in result.lower() or "inicial" in result.lower()


# ---------------------------------------------------------------------------
# validate_month
# ---------------------------------------------------------------------------

def test_validate_month_valid_returns_tuple():
    result = validate_month(date.today().year, 6)
    assert result == (date.today().year, 6)


def test_validate_month_month_out_of_bounds_returns_str():
    result = validate_month(date.today().year, 13)
    assert isinstance(result, str)
    assert "mes" in result.lower()


def test_validate_month_year_out_of_bounds_returns_str():
    result = validate_month(1900, 1)
    assert isinstance(result, str)
    assert "año" in result.lower() or "a" in result.lower()
