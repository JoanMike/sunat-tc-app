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

import json
import os
import random
import sqlite3
import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import requests

# Single source of truth for the application version (Q8 /
# quality-lint-and-hardening D4). Surfaced via the `--version` CLI flag
# (cli.py) and the "Acerca de" dialog (app.py). Supersedes the temporary
# `_APP_VERSION` placeholder from Change F.
__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Re-exports (submodules)
# ---------------------------------------------------------------------------

from .errors import FetchError  # noqa: F401  (public re-export)
from .locale import MONTHS_ABBR_ES, MONTHS_ES  # noqa: F401
from .messages import format_fetch_error  # noqa: F401  (Spanish FetchError mapper)
from .validators import MAX_RANGE_DAYS, MIN_YEAR, validate_month, validate_range  # noqa: F401

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

API_BASE = "https://api.apis.net.pe/v1/tipo-cambio-sunat"
HTTP_TIMEOUT = 15  # segundos
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def max_year() -> int:
    """Año actual; se computa fresh en cada llamada (no constante de módulo).

    Reemplaza el antiguo `MAX_YEAR` que se evaluaba una sola vez al
    importar y quedaba stale pasada la medianoche del 31 de diciembre
    (fix-data-layer-bugs D3). Long-running processes (e.g. la GUI abierta
    toda la noche) ven el límite superior del spinbox de año fresco en
    cada invocación.
    """
    return date.today().year

# Para "mes completo" decidimos que el cache es confiable si trae al menos
# estos días (un mes tiene entre 20 y 23 días hábiles aprox.).
MIN_DAYS_FOR_CACHED_MONTH = 15


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _app_data_dir() -> Path:
    """%APPDATA% en Windows, ~/.local/share en Linux/macOS.

    No realiza mkdir; usar _ensure_app_data_dir() antes de leer/escribir.
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        )
    return base / "sunat-tc-app"


def _ensure_app_data_dir() -> Path:
    """Crea el dir de datos si no existe; devuelve la ruta. Llamar antes de I/O."""
    path = _app_data_dir()
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
    # Explicit None check: `or` would treat numeric 0.0 as falsy and fall through
    # to the legacy English keys, dropping the actual 0-value rate.
    compra = item.get("compra")
    if compra is None:
        compra = item.get("buyPrice")
    venta = item.get("venta")
    if venta is None:
        venta = item.get("sellPrice")
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
    """GET con reintentos exponenciales + jitter. Lanza FetchError en falla persistente.

    404/204 no son errores: devuelven [] (legítimamente "sin datos").
    """
    delay = 0.5
    for attempt in range(max_retries):
        try:
            r = requests.get(API_BASE, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                raise FetchError(kind="network", message=str(exc)) from exc
            time.sleep(delay + random.uniform(0, delay))
            delay *= 2
            continue
        if r.status_code in (404, 204):
            return []
        if r.status_code in RETRYABLE_STATUS:
            if attempt == max_retries - 1:
                # 429 (rate limit) stays in RETRYABLE_STATUS so it benefits
                # from the existing exponential-backoff schedule, but the
                # terminal FetchError.kind is "rate_limit" so callers can
                # surface a "Demasiadas solicitudes…" message instead of
                # the generic "SUNAT no está disponible (HTTP 429)" text
                # that http_5xx would produce (fix-data-layer-bugs D1).
                if r.status_code == 429:
                    raise FetchError(
                        kind="rate_limit",
                        message=f"HTTP {r.status_code}",
                        status=r.status_code,
                    )
                raise FetchError(
                    kind="http_5xx",
                    message=f"HTTP {r.status_code}",
                    status=r.status_code,
                )
            time.sleep(delay + random.uniform(0, delay))
            delay *= 2
            continue
        if r.status_code >= 400:
            kind = "http_4xx" if r.status_code < 500 else "http_5xx"
            raise FetchError(
                kind=kind,
                message=f"HTTP {r.status_code}",
                status=r.status_code,
            )
        try:
            return _coerce_list(r.json())
        except ValueError as exc:
            raise FetchError(kind="parse", message=str(exc)) from exc
    # Inalcanzable: cada rama del bucle retorna o lanza.
    raise FetchError(kind="network", message="reintentos agotados")


# ---------------------------------------------------------------------------
# Cache SQLite
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    _ensure_app_data_dir()
    # Stateless file-existence guard (perf-cache-batching P2): run CREATE DDL
    # only when the DB file is missing. The check MUST happen before
    # `sqlite3.connect`, which creates the file itself. No module-level flag or
    # lock -> thread-safe by design; correctly re-runs DDL if the file is
    # deleted between calls. `IF NOT EXISTS` keeps it idempotent if two threads
    # race on a missing file. Known limitation: a file that exists but lacks the
    # `rates` table (manual tampering) skips DDL -> first cache_* call raises
    # OperationalError; acceptable for a single-user desktop app.
    if not CACHE_DB.exists():
        conn_init = sqlite3.connect(CACHE_DB)
        try:
            conn_init.execute(
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
            conn_init.execute(
                "CREATE INDEX IF NOT EXISTS idx_rates_fecha ON rates(fecha)"
            )
            conn_init.commit()
        finally:
            conn_init.close()
    return sqlite3.connect(CACHE_DB)


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
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    # end es exclusivo en SQL BETWEEN (que es inclusivo), así que restamos 1.
    end_inclusive = end - timedelta(days=1)
    return cache_get_range(start, end_inclusive)


def cache_put_many(
    rows: Iterable[tuple],
    source: str = "apis.net.pe",
) -> None:
    """Inserta/actualiza N filas con UNA conexión, UN `executemany` y UN commit.

    Cada tupla es `(fecha, compra, venta)` o `(fecha, compra, venta, source)`;
    si se omite `source` por fila, usa el `source` por defecto del argumento.
    Las semánticas de upsert (`ON CONFLICT(fecha) DO UPDATE`) son idénticas a
    `cache_put`. `fetched_at` se computa una vez por batch (semántica "filas
    traídas juntas"). Reemplaza el patrón anterior de una conexión por fila
    (perf-cache-batching P1).
    """
    rows_list = list(rows)
    if not rows_list:
        return
    conn = _connect()
    try:
        fetched_at = datetime.now().isoformat(timespec="seconds")
        conn.executemany(
            """
            INSERT INTO rates (fecha, compra, venta, source, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                compra=excluded.compra,
                venta=excluded.venta,
                source=excluded.source,
                fetched_at=excluded.fetched_at
            """,
            [
                (r[0], float(r[1]), float(r[2]), r[3] if len(r) > 3 else source, fetched_at)
                for r in rows_list
            ],
        )
        conn.commit()
    finally:
        conn.close()


def cache_put(fecha: str, compra: float, venta: float, source: str = "apis.net.pe") -> None:
    """Inserta/actualiza una fila. Thin wrapper sobre `cache_put_many` (P1)."""
    cache_put_many([(fecha, compra, venta, source)])


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
    if rows:
        cache_put_many([(r["fecha"], r["compra"], r["venta"]) for r in rows])
    return rows


def _fetch_month_with_flag(
    year: int,
    month: int,
    *,
    use_cache: bool = True,
) -> tuple[list[dict], bool]:
    """Consulta un mes y devuelve `(rows, network_happened)` (perf-cache-batching P3).

    Lee el caché UNA vez (vía `cache_get_month`), aplica el umbral
    `MIN_DAYS_FOR_CACHED_MONTH` y devuelve las filas junto con un flag que
    indica si ocurrió una llamada de red. Esto reemplaza el patrón anterior
    donde `fetch_range` pre-decidía con `_month_requires_network` (otra lectura
    de caché) y luego llamaba `fetch_month` (que releía el caché).

    `network_happened` es False sólo cuando el mes se sirve completo del caché;
    en cualquier otro caso (caché desactivado, mes actual, caché incompleto o
    respuesta de red vacía) es True, porque se hizo (o se intentó) una petición.
    """
    v = validate_month(year, month)
    if isinstance(v, str):
        raise FetchError(kind="input", message=v)
    year, month = v
    today_d = date.today()
    is_current_month = year == today_d.year and month == today_d.month
    if use_cache and not is_current_month:
        cached = cache_get_month(year, month)
        if len(cached) >= MIN_DAYS_FOR_CACHED_MONTH:
            return sorted(cached.values(), key=lambda x: x["fecha"]), False
    data = _get_with_retry({"year": year, "month": month})
    if not data:
        return [], True
    rows = [n for n in (_normalize_item(x) for x in data) if n]
    if rows:
        cache_put_many([(r["fecha"], r["compra"], r["venta"]) for r in rows])
    return rows, True


def fetch_month(year: int, month: int, *, use_cache: bool = True) -> list[dict]:
    """Consulta un mes. Para meses pasados, sirve del cache si está completo.

    Delega en `_fetch_month_with_flag` (P3) y devuelve sólo las filas,
    preservando el contrato público existente (GUI/CLI/tests).
    """
    rows, _ = _fetch_month_with_flag(year, month, use_cache=use_cache)
    return rows


def fetch_range(
    start: date,
    end: date,
    *,
    use_cache: bool = True,
    on_progress: Callable[[str, int], None] | None = None,
) -> list[dict]:
    """Consulta un rango recorriendo mes a mes.

    Atajo de cortesía: si el mes se sirve enteramente del caché (sin red),
    se omite el `sleep` trailing; si hubo red, se duerme 0.1s (P4). La lectura
    de caché por mes ocurre una sola vez dentro de `_fetch_month_with_flag` (P3).
    """
    v = validate_range(start, end)
    if isinstance(v, str):
        raise FetchError(kind="input", message=v)
    start, end = v
    # `validate_range` (arriba) is el único guard para `start > end`:
    # raises FetchError(kind="input"). No hace falta un `if end < start: return []`
    # post-validate — sería código muerto (fix-data-layer-bugs Q5).
    resultados: list[dict] = []
    y, m = start.year, start.month
    total_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    month_idx = 0
    while (y, m) <= (end.year, end.month):
        month_idx += 1
        if on_progress:
            nombre = MONTHS_ABBR_ES[m]
            on_progress(
                f"Consultando {nombre} {y} ({month_idx}/{total_months})…",
                len(resultados),
            )
        meses, network_happened = _fetch_month_with_flag(y, m, use_cache=use_cache)
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
        if network_happened:
            # apis.net.pe is a public free API; 0.1s stays polite. The backoff
            # in _get_with_retry already handles 429/5xx. A 2-year full miss
            # drops 7.2s -> 2.4s (perf-cache-batching P4).
            time.sleep(0.1)
    resultados.sort(key=lambda x: x["fecha"])
    if on_progress:
        on_progress("Procesando resultados…", len(resultados))
    return resultados


# ---------------------------------------------------------------------------
# Estado persistido (ventana, modo, fechas)
# ---------------------------------------------------------------------------

DEFAULT_STATE: dict = {
    "geometry": "850x600",
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
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Valid JSON is not enough — `state.json` could legitimately
        # contain `5`, `null`, `[1,2,3]`, etc. if a user edits it by
        # hand. `dict.update` would raise TypeError on any non-dict
        # payload; defend with an explicit shape check (B4/D5) and a
        # widened except tuple so the app keeps launching on a corrupt
        # file instead of crashing.
        if not isinstance(data, dict):
            return dict(DEFAULT_STATE)
        merged = dict(DEFAULT_STATE)
        merged.update(data)
        # sane defaults en valores faltantes
        if not isinstance(merged.get("mode"), str):
            merged["mode"] = "today"
        return merged
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return dict(DEFAULT_STATE)


def save_state(state: dict) -> bool:
    """Persiste el estado. Devuelve True si pudo escribir."""
    try:
        _ensure_app_data_dir()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False
