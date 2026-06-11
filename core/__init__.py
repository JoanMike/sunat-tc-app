"""
Capa de datos para sunat-tc-app: fetching, cache local SQLite y estado.

Funciones de fetching:
    - fetch_day(day_str)        -> lista de dicts {fecha, compra, venta}
    - fetch_month(year, month)
    - fetch_range(start, end, on_progress=...)

Cache local (SQLite en %APPDATA%/sunat-tc-app/cache.db):
    - cache_get / cache_get_range / cache_get_month
    - cache_put / cache_count / cache_clear
    - Las fechas pasadas se sirven del cache; "hoy" siempre se re-consulta.

Estado persistido (JSON en %APPDATA%/sunat-tc-app/state.json):
    - load_state() -> dict
    - save_state(state)
"""

from __future__ import annotations

import calendar
import json
import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import requests

# ---------------------------------------------------------------------------
# Re-exports (submodules)
# ---------------------------------------------------------------------------

from .errors import FetchError  # noqa: F401  (public re-export)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

API_BASE = "https://api.apis.net.pe/v1/tipo-cambio-sunat"
HTTP_TIMEOUT = 15  # segundos
MAX_YEAR = date.today().year
MIN_YEAR = 2000
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Para "mes completo" decidimos que el cache es confiable si trae al menos
# estos días (un mes tiene entre 20 y 23 días hábiles aprox.).
MIN_DAYS_FOR_CACHED_MONTH = 15


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _app_data_dir() -> Path:
    """%APPDATA% en Windows, ~/.local/share en Linux/macOS."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        )
    path = base / "sunat-tc-app"
    path.mkdir(parents=True, exist_ok=True)
    return path


CACHE_DB: Path = _app_data_dir() / "cache.db"
STATE_FILE: Path = _app_data_dir() / "state.json"


# ---------------------------------------------------------------------------
# Normalización / HTTP
# ---------------------------------------------------------------------------

def _normalize_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    fecha = item.get("fecha") or item.get("date")
    compra = item.get("compra") or item.get("buyPrice")
    venta = item.get("venta") or item.get("sellPrice")
    if not fecha or compra is None or venta is None:
        return None
    try:
        return {
            "fecha": str(fecha)[:10],
            "compra": float(compra),
            "venta": float(venta),
        }
    except (TypeError, ValueError):
        return None


def _coerce_list(data) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _get_with_retry(params: dict, max_retries: int = 3) -> list[dict]:
    """GET con reintentos exponenciales. Devuelve [] si no hay datos o se agotaron los reintentos."""
    delay = 0.5
    for _ in range(max_retries):
        try:
            r = requests.get(API_BASE, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code in (404, 204):
            return []
        if r.status_code in RETRYABLE_STATUS:
            time.sleep(delay)
            delay *= 2
            continue
        try:
            r.raise_for_status()
        except requests.HTTPError:
            return []
        try:
            return _coerce_list(r.json())
        except ValueError:
            return []
    return []


# ---------------------------------------------------------------------------
# Cache SQLite
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rates (
            fecha       TEXT PRIMARY KEY,
            compra      REAL NOT NULL,
            venta       REAL NOT NULL,
            source      TEXT,
            fetched_at  TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rates_fecha ON rates(fecha)")
    conn.commit()
    return conn


def cache_get(fecha: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT fecha, compra, venta, source, fetched_at "
            "FROM rates WHERE fecha = ?",
            (fecha,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "fecha": row[0],
        "compra": row[1],
        "venta": row[2],
        "source": row[3],
        "fetched_at": row[4],
    }


def cache_get_range(start: date, end: date) -> dict[str, dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT fecha, compra, venta, source, fetched_at "
            "FROM rates WHERE fecha BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    finally:
        conn.close()
    return {
        r[0]: {
            "fecha": r[0],
            "compra": r[1],
            "venta": r[2],
            "source": r[3],
            "fetched_at": r[4],
        }
        for r in rows
    }


def cache_get_month(year: int, month: int) -> dict[str, dict]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    # end es exclusivo en SQL BETWEEN (que es inclusivo), así que restamos 1.
    end_inclusive = end - timedelta(days=1)
    return cache_get_range(start, end_inclusive)


def cache_put(fecha: str, compra: float, venta: float, source: str = "apis.net.pe") -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO rates (fecha, compra, venta, source, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                compra=excluded.compra,
                venta=excluded.venta,
                source=excluded.source,
                fetched_at=excluded.fetched_at
            """,
            (
                fecha,
                float(compra),
                float(venta),
                source,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def cache_count() -> int:
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM rates").fetchone()[0]
    finally:
        conn.close()


def cache_date_range() -> tuple[str | None, str | None]:
    """Devuelve (fecha_min, fecha_max) en el cache, o (None, None) si está vacío."""
    conn = _connect()
    try:
        row = conn.execute("SELECT MIN(fecha), MAX(fecha) FROM rates").fetchone()
    finally:
        conn.close()
    return (row[0], row[1]) if row else (None, None)


def cache_clear() -> int:
    """Borra todas las entradas. Devuelve cuántas había."""
    conn = _connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM rates").fetchone()[0]
        conn.execute("DELETE FROM rates")
        conn.commit()
        return n
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fetching (con cache integrado)
# ---------------------------------------------------------------------------

def fetch_day(day_str: str, *, use_cache: bool = True) -> list[dict]:
    """Consulta un día. Usa cache salvo que use_cache=False o que sea hoy."""
    is_today = day_str == date.today().isoformat()
    if use_cache and not is_today:
        cached = cache_get(day_str)
        if cached:
            return [
                {
                    "fecha": cached["fecha"],
                    "compra": cached["compra"],
                    "venta": cached["venta"],
                }
            ]
    data = _get_with_retry({"date": day_str})
    if not data:
        return []
    rows = [n for n in (_normalize_item(x) for x in data) if n]
    for r in rows:
        cache_put(r["fecha"], r["compra"], r["venta"])
    return rows


def fetch_month(year: int, month: int, *, use_cache: bool = True) -> list[dict]:
    """Consulta un mes. Para meses pasados, sirve del cache si está completo."""
    today_d = date.today()
    is_current_month = year == today_d.year and month == today_d.month
    if use_cache and not is_current_month:
        cached = cache_get_month(year, month)
        if len(cached) >= MIN_DAYS_FOR_CACHED_MONTH:
            return sorted(cached.values(), key=lambda x: x["fecha"])
    data = _get_with_retry({"year": year, "month": month})
    if not data:
        return []
    rows = [n for n in (_normalize_item(x) for x in data) if n]
    for r in rows:
        cache_put(r["fecha"], r["compra"], r["venta"])
    return rows


def fetch_range(
    start: date,
    end: date,
    *,
    use_cache: bool = True,
    on_progress: Callable[[str, int], None] | None = None,
) -> list[dict]:
    """Consulta un rango recorriendo mes a mes."""
    if end < start:
        return []
    resultados: list[dict] = []
    y, m = start.year, start.month
    total_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    month_idx = 0
    while (y, m) <= (end.year, end.month):
        month_idx += 1
        if on_progress:
            nombre = calendar.month_abbr[m]
            on_progress(
                f"Consultando {nombre} {y} ({month_idx}/{total_months})…",
                len(resultados),
            )
        meses = fetch_month(y, m, use_cache=use_cache)
        for item in meses:
            try:
                d = datetime.strptime(item["fecha"], "%Y-%m-%d").date()
            except ValueError:
                continue
            if start <= d <= end:
                resultados.append(item)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
        time.sleep(0.3)  # cortesía
    resultados.sort(key=lambda x: x["fecha"])
    if on_progress:
        on_progress("Procesando resultados…", len(resultados))
    return resultados


# ---------------------------------------------------------------------------
# Estado persistido (ventana, modo, fechas)
# ---------------------------------------------------------------------------

DEFAULT_STATE: dict = {
    "geometry": "720x600",
    "mode": "today",
    "range_start": None,
    "range_end": None,
    "month": date.today().month,
    "year": date.today().year,
}


def load_state() -> dict:
    if not STATE_FILE.exists():
        return dict(DEFAULT_STATE)
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_STATE)
        merged.update(data)
        # sane defaults en valores faltantes
        if not isinstance(merged.get("mode"), str):
            merged["mode"] = "today"
        return merged
    except (OSError, json.JSONDecodeError, ValueError):
        return dict(DEFAULT_STATE)


def save_state(state: dict) -> bool:
    """Persiste el estado. Devuelve True si pudo escribir."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False
