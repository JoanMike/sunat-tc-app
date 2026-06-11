"""Failing tests for core/locale.py (TDD RED — T1.3).

These tests will fail until core/locale.py is created in T1.7.
"""
from __future__ import annotations

import pytest


def test_months_es_full_names_exist():
    """MONTHS_ES must export 13 slots (index 0 unused) with Spanish full names."""
    from core import MONTHS_ES  # noqa: WPS433 — TDD import

    assert len(MONTHS_ES) == 13
    assert MONTHS_ES[1] == "Enero"
    assert MONTHS_ES[2] == "Febrero"
    assert MONTHS_ES[3] == "Marzo"
    assert MONTHS_ES[4] == "Abril"
    assert MONTHS_ES[5] == "Mayo"
    assert MONTHS_ES[6] == "Junio"
    assert MONTHS_ES[7] == "Julio"
    assert MONTHS_ES[8] == "Agosto"
    assert MONTHS_ES[9] == "Septiembre"
    assert MONTHS_ES[10] == "Octubre"
    assert MONTHS_ES[11] == "Noviembre"
    assert MONTHS_ES[12] == "Diciembre"


def test_months_abbr_es_abbreviated_names_exist():
    """MONTHS_ABBR_ES must export 13 slots with Spanish abbreviated names."""
    from core import MONTHS_ABBR_ES  # noqa: WPS433

    assert len(MONTHS_ABBR_ES) == 13
    assert MONTHS_ABBR_ES[1] == "Ene"
    assert MONTHS_ABBR_ES[2] == "Feb"
    assert MONTHS_ABBR_ES[3] == "Mar"
    assert MONTHS_ABBR_ES[4] == "Abr"
    assert MONTHS_ABBR_ES[5] == "May"
    assert MONTHS_ABBR_ES[6] == "Jun"
    assert MONTHS_ABBR_ES[7] == "Jul"
    assert MONTHS_ABBR_ES[8] == "Ago"
    assert MONTHS_ABBR_ES[9] == "Sep"
    assert MONTHS_ABBR_ES[10] == "Oct"
    assert MONTHS_ABBR_ES[11] == "Nov"
    assert MONTHS_ABBR_ES[12] == "Dic"
