"""Spanish locale data: month names.

Lists are 13-element with index 0 unused, so callers can index by
datetime.month directly (1..12).
"""
from __future__ import annotations

MONTHS_ABBR_ES: list[str] = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
                              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

MONTHS_ES: list[str] = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
