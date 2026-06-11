"""Input validation helpers used by both core fetch_* and CLI / GUI.

Funciones públicas:
    - validate_range(start, end) -> tuple[date, date] | str
    - validate_month(year, month) -> tuple[int, int] | str

En caso de error, devuelven un mensaje en español (string). En caso de
éxito, devuelven una tupla con los valores normalizados.
"""
from __future__ import annotations

from datetime import date

# Constantes del dominio (clamp histórico + máximo dinámico).
MIN_YEAR = 2000
MIN_RANGE_DAYS = 1
MAX_RANGE_DAYS = 730  # ≈ 2 años


def _max_year() -> int:
    """Año actual; se computa fresh en cada llamada (no es constante de módulo)."""
    return date.today().year


def validate_range(start: date, end: date) -> tuple[date, date] | str:
    if start > end:
        return "La fecha inicial no puede ser posterior a la final."
    if end > date.today():
        return "La fecha final no puede ser futura."
    if (end - start).days > MAX_RANGE_DAYS:
        return f"El rango máximo es de 2 años ({MAX_RANGE_DAYS} días)."
    return (start, end)


def validate_month(year: int, month: int) -> tuple[int, int] | str:
    if not (1 <= month <= 12):
        return "El mes debe estar entre 1 y 12."
    if not (MIN_YEAR <= year <= _max_year()):
        return f"El año debe estar entre {MIN_YEAR} y {_max_year()}."
    return (year, month)
