"""
Capa de datos para sunat-tc-app: fetching, cache local SQLite, estado y token.

Funciones de fetching:
    - fetch_day(day_str)        -> lista de dicts {fecha, compra, venta}
    - fetch_month(year, month)
    - fetch_range(start, end, on_progress=...)

APIs:
    - v1 pública (sin token): https://api.apis.net.pe/v1/tipo-cambio-sunat.
      Sólo respeta `?fecha=YYYY-MM-DD` (un día) y limita ~20 req/min por IP,
      así que mes/rango se reconstruyen día a día (lento pero sin token).
    - v2 con token (opcional): devuelve el mes completo en UNA petición.
      El token se configura en «Configurar token…» (GUI) y se guarda en
      config.json junto al caché; la variable de entorno SUNAT_TC_TOKEN
      tiene prioridad y el token nunca se escribe en logs ni en el código.

Cache local (SQLite en %APPDATA%/sunat-tc-app/cache.db):
    - cache_get / cache_get_range / cache_get_month
    - cache_put / cache_count / cache_clear
    - Las fechas pasadas se sirven del cache; "hoy" siempre se re-consulta.

Estado persistido (JSON en %APPDATA%/sunat-tc-app/state.json):
    - load_state() -> dict
    - save_state(state)

Config local (JSON en %APPDATA%/sunat-tc-app/config.json):
    - load_token() / save_token(token) / get_api_token() / check_token(token)
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import random
import re
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
# API v2 (token opcional). Devuelve el mes completo en una sola petición
# (`?month=&year=`) y un día con `?date=`. Mismo token para ambos endpoints
# v2 probados (decolecta y api.apis.net.pe/v2); se usa el documentado hoy.
API_V2_BASE = "https://api.decolecta.com/v1/tipo-cambio/sunat"
HTTP_TIMEOUT = 15  # segundos
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Logger de la capa de datos. Hijo de "sunat_tc_app" (app.py); el handler
# a archivo lo instala setup_logging() desde los entry points.
_logger = logging.getLogger("sunat_tc_app.core")

# Fechas ISO estrictas (YYYY-MM-DD). _normalize_item rechaza cualquier otra
# cosa antes de que llegue al caché o a los exports CSV/XLSX — un string
# que empiece por =, +, - o @ sería ejecutado por Excel como fórmula
# (hardening contra CSV/formula injection vía la API upstream).
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def max_year() -> int:
    """Año actual; se computa fresh en cada llamada (no constante de módulo).

    Reemplaza el antiguo `MAX_YEAR` que se evaluaba una sola vez al
    importar y quedaba stale pasada la medianoche del 31 de diciembre
    (fix-data-layer-bugs D3). Long-running processes (e.g. la GUI abierta
    toda la noche) ven el límite superior del spinbox de año fresco en
    cada invocación.
    """
    return date.today().year

# La API v1 pública no respeta `?month=&year=` (responde con el TC de hoy,
# ignorando los parámetros) y su nginx limita ~20 req/min por IP (HTTP 429).
# Sin token, los meses se reconstruyen pidiendo día a día con `?fecha=`, así
# que el espaciado entre peticiones de red consecutivas debe respetar ese
# límite (~1 token cada 3s, medido empíricamente contra el API real).
# Con token (API v2) el mes llega en UNA petición y este pacing no aplica.
DAY_REQUEST_DELAY = 3.2  # segundos entre peticiones de red consecutivas (v1)


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
# Config local (token de la API v2). Nunca vive en el repositorio.
CONFIG_FILE: Path = _app_data_dir() / "config.json"


def setup_logging(level: int = logging.INFO) -> None:
    """Adjunta un handler de archivo rotativo al logger raíz de la app.

    Idempotente: si ya hay un RotatingFileHandler instalado, no añade otro
    (los tests llaman a los entry points muchas veces por sesión). El log
    vive junto a state.json (`STATE_FILE.parent`), así los tests que
    parchean STATE_FILE a un tmp_path no escriben en el %APPDATA% real.
    Lo llaman los entry points (`app.main`, `cli.run`); importar el módulo
    no tiene side effects de logging.
    """
    from logging.handlers import RotatingFileHandler

    logger = logging.getLogger("sunat_tc_app")
    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return
    log_dir = STATE_FILE.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level)


# ---------------------------------------------------------------------------
# Normalización / HTTP
# ---------------------------------------------------------------------------

def _first_present(item: dict, *keys: str):
    """Primer valor presente (no None) entre `keys`.

    Se usa en lugar de `or` para no descartar el 0 numérico (falsy) de una
    tasa real; ver `_normalize_item`.
    """
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _normalize_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    # v1: fecha/compra/venta y buyPrice/sellPrice; v2 (decolecta):
    # date/buy_price/sell_price; v2 (api.apis.net.pe): fecha/precioCompra/precioVenta.
    fecha = _first_present(item, "fecha", "date")
    compra = _first_present(item, "compra", "buyPrice", "buy_price", "precioCompra")
    venta = _first_present(item, "venta", "sellPrice", "sell_price", "precioVenta")
    if not fecha or compra is None or venta is None:
        return None
    fecha_str = str(fecha)[:10]
    # Rechazo temprano de fechas no-ISO (ver _ISO_DATE_RE): evita que un
    # string hostil llegue verbatim a los exports CSV/XLSX.
    if not _ISO_DATE_RE.match(fecha_str):
        return None
    try:
        return {
            "fecha": fecha_str,
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


def _request_with_retry(
    url: str,
    params: dict,
    *,
    headers: dict | None = None,
    max_retries: int = 3,
) -> list[dict]:
    """GET con reintentos exponenciales + jitter. Lanza FetchError en falla persistente.

    404/204 no son errores: devuelven [] (legítimamente "sin datos").
    Los `headers` (p. ej. el Bearer token) nunca se loguean.
    """
    delay = 0.5
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                _logger.error(
                    "GET %s %s: red agotada tras %d intentos: %s",
                    url, params, max_retries, exc,
                )
                raise FetchError(kind="network", message=str(exc)) from exc
            _logger.warning(
                "GET %s %s: intento %d/%d falló (%s); reintento en %.1fs",
                url, params, attempt + 1, max_retries, exc, delay,
            )
            time.sleep(delay + random.uniform(0, delay))
            delay *= 2
            continue
        if r.status_code in (404, 204):
            return []
        if r.status_code in RETRYABLE_STATUS:
            if attempt == max_retries - 1:
                _logger.error(
                    "GET %s %s: HTTP %d persistente tras %d intentos",
                    url, params, r.status_code, max_retries,
                )
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
            _logger.warning(
                "GET %s %s: HTTP %d (intento %d/%d); reintento en %.1fs",
                url, params, r.status_code, attempt + 1, max_retries, delay,
            )
            time.sleep(delay + random.uniform(0, delay))
            delay *= 2
            continue
        if r.status_code >= 400:
            kind = "http_4xx" if r.status_code < 500 else "http_5xx"
            _logger.error(
                "GET %s %s: HTTP %d no reintentable", url, params, r.status_code
            )
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


def _get_with_retry(params: dict, max_retries: int = 3) -> list[dict]:
    """GET a la API pública v1 (sin token); ver `_request_with_retry`."""
    return _request_with_retry(API_BASE, params, max_retries=max_retries)


def _get_v2_with_retry(params: dict, token: str, max_retries: int = 3) -> list[dict]:
    """GET a la API v2 con `Authorization: Bearer <token>`.

    401/403 se mapean a `FetchError(kind="auth")` SIN reintentar: indican
    token inválido/vencido (o cuota agotada), no un fallo transitorio. El
    resto de errores conserva la semántica de `_request_with_retry`.
    """
    try:
        return _request_with_retry(
            API_V2_BASE,
            params,
            headers={"Authorization": f"Bearer {token}"},
            max_retries=max_retries,
        )
    except FetchError as exc:
        if exc.status in (401, 403):
            raise FetchError(kind="auth", message=str(exc), status=exc.status) from exc
        raise


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
# Token de la API v2 (config local)
# ---------------------------------------------------------------------------

def load_token() -> str | None:
    """Lee el token desde config.json (None si no hay o el archivo es inválido)."""
    if not CONFIG_FILE.exists():
        return None
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if not isinstance(token, str):
        return None
    return token.strip() or None


def save_token(token: str | None) -> bool:
    """Guarda (o borra, con None/"") el token en config.json. True si pudo escribir.

    El token vive sólo en %APPDATA%/sunat-tc-app/config.json: nunca en el
    repositorio, el estado de la ventana ni los logs.
    """
    try:
        _ensure_app_data_dir()
        data: dict = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict):
                    data = existing
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                data = {}
        value = (token or "").strip()
        if value:
            data["token"] = value
        else:
            data.pop("token", None)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


def get_api_token() -> str | None:
    """Token vigente: SUNAT_TC_TOKEN (entorno) > config.json > None."""
    env = os.environ.get("SUNAT_TC_TOKEN", "").strip()
    if env:
        return env
    return load_token()


def check_token(token: str) -> bool | None:
    """Verifica el token contra la API v2 (1 petición al endpoint de hoy).

    True = aceptado; False = rechazado (401/403: inválido, vencido o sin
    cuota); None = no verificable (sin conexión u otro error transitorio).
    """
    try:
        _get_v2_with_retry({}, token, max_retries=1)
        return True
    except FetchError as exc:
        return False if exc.kind == "auth" else None


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
    data = _get_with_retry({"fecha": day_str})
    if not data:
        return []
    # Sólo se acepta el día solicitado: si la API ignorara `fecha` (como
    # hace con `month`/`year`) devolvería el TC de hoy y se cachearía una
    # fecha equivocada (ver `_fetch_month_with_flag`).
    rows = [
        n
        for n in (_normalize_item(x) for x in data)
        if n and n["fecha"] == day_str
    ]
    if rows:
        cache_put_many([(r["fecha"], r["compra"], r["venta"]) for r in rows])
    return rows


def _fetch_month_with_flag(
    year: int,
    month: int,
    *,
    use_cache: bool = True,
    start: date | None = None,
    end: date | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> tuple[list[dict], bool]:
    """Consulta un mes (o el subrango `[start, end]` dentro de él) y devuelve
    `(rows, network_happened)`.

    Con token (`get_api_token`) se usa la API v2: el mes completo llega en UNA
    petición (`?month=&year=`). Sin token se usa la API pública v1, que ya no
    soporta `?month=&year=` (responde con el TC de hoy sin importar los
    parámetros): el mes se reconstruye pidiendo día a día con `?fecha=`, el
    único filtro que la v1 respeta. En ambos modos se descartan los payloads
    cuya fecha quede fuera de la ventana solicitada, para que una respuesta
    "de hoy" (o de otro mes) nunca se cuele ni se cachee con otra fecha.

    Cache: los días ya cacheados se reutilizan (excepto "hoy", que siempre se
    re-consulta) y sólo se piden a la red los días faltantes; si la ventana
    está completa en el caché no se toca la red. `use_cache=False` ignora el
    caché por completo. `network_happened` es False sólo cuando no se hizo
    ninguna petición de red.

    Pacing v1: la API pública limita ~20 req/min por IP (nginx responde 429,
    ver `DAY_REQUEST_DELAY`), así que se espera entre peticiones consecutivas.
    `on_progress(msg, count)` se llama antes de cada petición de red del modo
    v1 (la GUI lo usa para pintar el día en curso y cancelar cooperativamente).
    """
    v = validate_month(year, month)
    if isinstance(v, str):
        raise FetchError(kind="input", message=v)
    year, month = v
    today_d = date.today()
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    # Nunca pedir fechas futuras: el mes en curso termina hoy.
    last = min(last, today_d)
    if start is not None:
        first = max(first, start)
    if end is not None:
        last = min(last, end)
    if first > last:
        return [], False

    cached = cache_get_month(year, month) if use_cache else {}
    token = get_api_token()
    rows: dict[str, dict] = {}
    fetched: list[dict] = []
    network_happened = False
    window_days = [
        first + timedelta(days=i) for i in range((last - first).days + 1)
    ]

    if token:
        # API v2 (con token): el mes llega completo en UNA petición. Si todos
        # los días de la ventana ya están cacheados (y hoy no está entre
        # ellos), se responde del caché sin tocar la red.
        missing = [
            d
            for d in window_days
            if not (use_cache and d < today_d and d.isoformat() in cached)
        ]
        if not missing:
            return (
                sorted(
                    (cached[d.isoformat()] for d in window_days),
                    key=lambda x: x["fecha"],
                ),
                False,
            )
        data = _get_v2_with_retry({"year": year, "month": month}, token)
        network_happened = True
        first_iso, last_iso = first.isoformat(), last.isoformat()
        for item in data:
            n = _normalize_item(item)
            # Sólo días dentro de la ventana: si la API ignorara month/year
            # (como la v1), su respuesta "de hoy" no se cuela ni se cachea.
            if n and first_iso <= n["fecha"] <= last_iso:
                rows[n["fecha"]] = n
                fetched.append(n)
        # Huecos de la respuesta se completan con días cacheados previos.
        for d in window_days:
            iso = d.isoformat()
            if iso not in rows and use_cache and d < today_d and iso in cached:
                rows[iso] = cached[iso]
    else:
        # API pública v1 (sin token): se pide día a día con pacing para no
        # chocar con el límite de ~20 req/min por IP.
        day = first
        while day <= last:
            iso = day.isoformat()
            if use_cache and day < today_d and iso in cached:
                rows[iso] = cached[iso]
            else:
                if network_happened:
                    time.sleep(DAY_REQUEST_DELAY)
                if on_progress:
                    on_progress(f"Consultando {day.strftime('%d/%m/%Y')}…", len(rows))
                data = _get_with_retry({"fecha": iso})
                network_happened = True
                for item in data:
                    n = _normalize_item(item)
                    if n and n["fecha"] == iso:
                        rows[iso] = n
                        fetched.append(n)
            day += timedelta(days=1)
    if fetched:
        cache_put_many([(r["fecha"], r["compra"], r["venta"]) for r in fetched])
    return sorted(rows.values(), key=lambda x: x["fecha"]), network_happened


def fetch_month(
    year: int,
    month: int,
    *,
    use_cache: bool = True,
    on_progress: Callable[[str, int], None] | None = None,
) -> list[dict]:
    """Consulta un mes. Sirve del caché los días ya consultados.

    Con token configurado usa la API v2 (1 petición por mes); sin token
    reconstruye el mes día a día contra la API pública v1. Delega en
    `_fetch_month_with_flag` y devuelve sólo las filas, preservando el
    contrato público existente (GUI/CLI/tests). `on_progress` es opcional
    (ticks por día de red del modo v1; la GUI lo usa para progreso y
    cancelación).
    """
    rows, _ = _fetch_month_with_flag(
        year, month, use_cache=use_cache, on_progress=on_progress
    )
    return rows


def fetch_range(
    start: date,
    end: date,
    *,
    use_cache: bool = True,
    on_progress: Callable[[str, int], None] | None = None,
) -> list[dict]:
    """Consulta un rango recorriendo mes a mes (día a día dentro de cada mes).

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
        # `start`/`end` acotan la red a los días del rango: sin esto, un
        # rango de 3 días pediría el mes completo (~30 peticiones).
        meses, network_happened = _fetch_month_with_flag(
            y, m, use_cache=use_cache, start=start, end=end
        )
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
