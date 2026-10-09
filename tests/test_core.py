"""Failing tests for core.py behavior changes (TDD RED — T1.3).

These tests are written BEFORE the corresponding implementation commits
(T1.4-T1.7). They will fail because:
- FetchError doesn't exist yet (T1.4)
- _get_with_retry still returns [] on failure (T1.5)
- fetch_range still sleeps unconditionally (T1.6)
- _normalize_item still uses `or` for numeric zero (T1.7)
"""
from __future__ import annotations

from datetime import date, timedelta
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


def test_retry_429_raises_rate_limit_after_exhaustion(monkeypatch):
    """HTTP 429 x3 must raise FetchError(kind='rate_limit') (B1).

    429 stays in RETRYABLE_STATUS (still retried) but the terminal kind
    distinguishes it from generic 5xx so the user sees a rate-limit
    message, not "SUNAT unavailable".
    """
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    assert 429 in core.RETRYABLE_STATUS, (
        "429 must remain in RETRYABLE_STATUS for the retry-then-raise pattern"
    )
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, status_code=429)
        with pytest.raises(core.FetchError) as exc_info:
            core._get_with_retry({"date": "2024-01-15"}, max_retries=3)
        assert exc_info.value.kind == "rate_limit", (
            f"expected kind='rate_limit' after 429 exhaustion, got {exc_info.value.kind!r}"
        )
        assert exc_info.value.status == 429
        assert m.call_count == 3


def test_retry_5xx_exhausted_still_raises_http_5xx(monkeypatch):
    """Non-429 5xx exhaustion must still raise kind='http_5xx' (B1 regression).

    Guards against the 429 branch swallowing the generic 5xx raise path.
    """
    monkeypatch.setattr("core.time.sleep", lambda _d: None)
    with requests_mock.Mocker() as m:
        m.get(core.API_BASE, status_code=503)
        with pytest.raises(core.FetchError) as exc_info:
            core._get_with_retry({"date": "2024-01-15"}, max_retries=3)
        assert exc_info.value.kind == "http_5xx"
        assert exc_info.value.status == 503
        assert m.call_count == 3


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
# perf-cache-batching (Change E) — P1: batched cache writes via cache_put_many
# ---------------------------------------------------------------------------

def test_cache_put_many_uses_one_connection(monkeypatch, tmp_cache_dir):
    """cache_put_many must open exactly one SQLite connection for N rows (P1).

    Replaces the per-row `cache_put` pattern that opened one connection per
    row. We wrap `core._connect` with a counter that still delegates to the
    real connection (real SQLite on the tmp_path DB), insert 20 rows, and
    assert `_connect` was called exactly once.
    """
    calls = {"n": 0}
    real_connect = core._connect

    def counting_connect():
        calls["n"] += 1
        return real_connect()

    monkeypatch.setattr(core, "_connect", counting_connect)
    rows = [
        (f"2024-01-{d:02d}", 3.70 + d * 0.001, 3.75 + d * 0.001, "test")
        for d in range(1, 21)
    ]
    core.cache_put_many(rows)
    assert calls["n"] == 1, (
        f"cache_put_many must use one connection for 20 rows, got {calls['n']}"
    )


def test_cache_put_many_upserts_on_conflict(tmp_cache_dir):
    """cache_put_many must upsert on conflicting fecha (ON CONFLICT DO UPDATE)."""
    core.cache_put("2024-01-15", 1.0, 1.1, source="old")
    core.cache_put_many([("2024-01-15", 2.0, 2.1, "new")])
    row = core.cache_get("2024-01-15")
    assert row is not None, "upserted row must exist"
    assert row["compra"] == 2.0, f"compra must be updated to 2.0, got {row['compra']}"
    assert row["venta"] == 2.1, f"venta must be updated to 2.1, got {row['venta']}"
    assert row["source"] == "new", f"source must be updated to 'new', got {row['source']!r}"


def test_cache_put_still_works_single_row(tmp_cache_dir):
    """cache_put single-row wrapper must still round-trip after the refactor.

    Approval/regression guard: `cache_put` becomes a thin wrapper over
    `cache_put_many`, so the single-row contract must not change.
    """
    core.cache_put("2024-01-15", 3.74, 3.75, source="test")
    row = core.cache_get("2024-01-15")
    assert row is not None
    assert row["fecha"] == "2024-01-15"
    assert row["compra"] == 3.74
    assert row["venta"] == 3.75
    assert row["source"] == "test"


def test_fetch_month_batches_cache_writes(monkeypatch, tmp_cache_dir):
    """fetch_month must write the network response via one cache_put_many call.

    La API no soporta `?month=&year=`, así que el mes se pide día a día con
    `?fecha=`; el mock devuelve las 20 filas para cualquier día y el filtro
    de fecha estricto deja exactamente esas 20, escritas en un solo batch.
    """
    rows_data = [
        {"fecha": f"2024-01-{d:02d}", "compra": 3.70, "venta": 3.75}
        for d in range(1, 21)
    ]
    monkeypatch.setattr(core, "_get_with_retry", lambda params, **kw: rows_data)
    monkeypatch.setattr(core.time, "sleep", lambda _d: None)
    calls: list = []
    monkeypatch.setattr(
        core, "cache_put_many", lambda *a, **k: calls.append(a), raising=False
    )
    core.fetch_month(2024, 1)
    assert len(calls) == 1, (
        f"fetch_month must call cache_put_many once for a 20-row response, "
        f"got {len(calls)}"
    )


def test_fetch_month_requests_each_day_via_fecha(monkeypatch, tmp_cache_dir):
    """El mes se pide día a día con `?fecha=` (la API v1 no soporta month/year)."""
    asked: list[dict] = []

    def fake_get(params, **kw):
        asked.append(params)
        return [{"fecha": params["fecha"], "compra": 3.70, "venta": 3.75}]

    monkeypatch.setattr(core, "_get_with_retry", fake_get)
    monkeypatch.setattr(core.time, "sleep", lambda _d: None)

    rows = core.fetch_month(2024, 1)

    assert len(asked) == 31, f"enero tiene 31 días, got {asked}"
    assert asked[0] == {"fecha": "2024-01-01"}
    assert asked[-1] == {"fecha": "2024-01-31"}
    assert [r["fecha"] for r in rows] == [f"2024-01-{d:02d}" for d in range(1, 32)]


def test_fetch_month_discards_wrong_date_payloads(monkeypatch, tmp_cache_dir):
    """Una respuesta "de hoy" que ignore `fecha` no debe colarse ni cachearse.

    Regresión del bug reportado: `?month=&year=` devolvía sólo el TC de hoy.
    Si la API ignorara también `fecha`, `fetch_month` debe devolver [] en vez
    de mostrar/cachear el TC de hoy bajo otro mes.
    """
    today_row = {"fecha": date.today().isoformat(), "compra": 3.44, "venta": 3.45}
    monkeypatch.setattr(core, "_get_with_retry", lambda params, **kw: [today_row])
    monkeypatch.setattr(core.time, "sleep", lambda _d: None)
    put_calls: list = []
    monkeypatch.setattr(core, "cache_put_many", lambda *a, **k: put_calls.append(a))

    rows = core.fetch_month(2024, 1)  # enero 2024 nunca es "hoy"

    assert rows == [], f"filas con fecha ajena deben descartarse, got {rows}"
    assert put_calls == [], "no debe cachearse una fila con fecha equivocada"


def test_fetch_month_reuses_cached_days_and_fetches_missing(monkeypatch, tmp_cache_dir):
    """Los días ya cacheados no se re-piden; sólo los faltantes van a la red."""
    core.cache_put("2024-01-05", 3.70, 3.75)
    core.cache_put("2024-01-20", 3.71, 3.76)
    asked: list[str] = []

    def fake_get(params, **kw):
        asked.append(params["fecha"])
        return [{"fecha": params["fecha"], "compra": 3.70, "venta": 3.75}]

    monkeypatch.setattr(core, "_get_with_retry", fake_get)
    monkeypatch.setattr(core.time, "sleep", lambda _d: None)

    rows = core.fetch_month(2024, 1)

    assert "2024-01-05" not in asked and "2024-01-20" not in asked, (
        f"días cacheados no deben re-pedirse, asked={asked}"
    )
    assert len(asked) == 29, f"31 días - 2 cacheados = 29 peticiones, got {asked}"
    assert len(rows) == 31
    assert [r["fecha"] for r in rows] == [f"2024-01-{d:02d}" for d in range(1, 32)]


def test_fetch_month_always_refetches_today(monkeypatch, tmp_cache_dir):
    """El día de hoy se re-consulta a la red aunque esté cacheado."""
    today = date.today()
    core.cache_put(today.isoformat(), 1.0, 1.1)
    asked: list[str] = []

    def fake_get(params, **kw):
        asked.append(params["fecha"])
        return [{"fecha": params["fecha"], "compra": 3.44, "venta": 3.45}]

    monkeypatch.setattr(core, "_get_with_retry", fake_get)
    monkeypatch.setattr(core.time, "sleep", lambda _d: None)

    rows = core.fetch_month(today.year, today.month)

    assert today.isoformat() in asked, "hoy debe re-consultarse a la red"
    hoy = [r for r in rows if r["fecha"] == today.isoformat()]
    assert hoy and hoy[0]["compra"] == 3.44, (
        f"hoy debe reflejar el valor fresco de la red, got {hoy}"
    )


def test_fetch_month_paces_network_requests(monkeypatch, tmp_cache_dir):
    """Entre peticiones de red consecutivas se espera DAY_REQUEST_DELAY (429-safe)."""
    monkeypatch.setattr(core, "DAY_REQUEST_DELAY", 1.5)
    monkeypatch.setattr(
        core,
        "_get_with_retry",
        lambda params, **kw: [
            {"fecha": params["fecha"], "compra": 3.7, "venta": 3.8}
        ],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(core.time, "sleep", lambda d: sleeps.append(d))

    core.fetch_month(2024, 2)  # 29 días -> 28 esperas entre peticiones

    assert sleeps == [1.5] * 28, (
        f"debe esperar entre peticiones consecutivas (n-1 veces), got {sleeps}"
    )


# ---------------------------------------------------------------------------
# perf-cache-batching (Change E) — P2: schema DDL only when DB file missing
# ---------------------------------------------------------------------------

def _spy_connect_factory(spies: list):
    """Return a `sqlite3.connect` replacement that wraps each real connection in
    a `MagicMock(wraps=...)` so `execute`/`commit`/`close` forward to the real
    SQLite connection while every `execute` call is recorded for inspection.

    `sqlite3.Connection.execute` is read-only, so we cannot patch it on the real
    connection directly; `MagicMock(wraps=conn)` records and forwards cleanly.
    Each created mock is appended to `spies` so the test can inspect
    `mock.execute.call_args_list`.
    """
    real_connect = core.sqlite3.connect

    def spy_connect(path, *args, **kwargs):
        mock_conn = MagicMock(wraps=real_connect(path, *args, **kwargs))
        spies.append(mock_conn)
        return mock_conn

    return spy_connect


def _ddl_execute_sqls(mock_conn) -> list:
    """Extract CREATE TABLE / CREATE INDEX SQL strings from a spied connection."""
    ddl = []
    for call in mock_conn.execute.call_args_list:
        sql = call.args[0] if call.args else call.kwargs.get("sql", "")
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql:
            ddl.append(sql)
    return ddl


def test_connect_skips_ddl_when_db_exists(monkeypatch, tmp_cache_dir):
    """A second `_connect` (DB file already present) must NOT run CREATE DDL (P2)."""
    cache_db, _ = tmp_cache_dir
    # First call creates the file + initializes the schema (DDL runs here).
    c0 = core._connect()
    c0.close()
    assert cache_db.exists(), "first _connect must create the DB file"

    # Spy on the SECOND call's execute statements.
    spies: list = []
    monkeypatch.setattr(core.sqlite3, "connect", _spy_connect_factory(spies))
    c1 = core._connect()
    c1.close()

    assert len(spies) == 1, (
        f"expected one connect on the second _connect, got {len(spies)}"
    )
    ddl_calls = _ddl_execute_sqls(spies[0])
    assert ddl_calls == [], (
        f"second _connect on an existing DB must skip DDL, got {ddl_calls}"
    )


def test_connect_runs_ddl_when_db_missing(monkeypatch, tmp_cache_dir):
    """The first `_connect` on a missing DB file must run CREATE TABLE + CREATE INDEX (P2)."""
    cache_db, _ = tmp_cache_dir
    assert not cache_db.exists(), "fixture must start with no DB file"

    spies: list = []
    monkeypatch.setattr(core.sqlite3, "connect", _spy_connect_factory(spies))
    c = core._connect()
    c.close()

    assert cache_db.exists(), "first _connect must create the DB file"
    # The missing-file path may open more than one connection (an init
    # connection for DDL + the returned connection); the spec scenario is
    # "DDL runs and the file is created", so we aggregate CREATE statements
    # across all spied connections rather than asserting a connect count.
    all_ddl = [sql for spy in spies for sql in _ddl_execute_sqls(spy)]
    assert any("CREATE TABLE" in s for s in all_ddl), (
        f"first _connect on missing file must run CREATE TABLE, got {all_ddl}"
    )
    assert any("CREATE INDEX" in s for s in all_ddl), (
        f"first _connect on missing file must run CREATE INDEX, got {all_ddl}"
    )


# ---------------------------------------------------------------------------
# Cache-hit short-circuit in fetch_range
# ---------------------------------------------------------------------------

def test_fetch_range_cache_hit_skips_sleep(monkeypatch, tmp_cache_dir):
    """When a month is fully cached, fetch_range must not call time.sleep."""
    # Pre-populate cache for January 2024 (la ventana 1-15 queda completa)
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


# ---------------------------------------------------------------------------
# perf-cache-batching (Change E) — P3: single cache read per month + P4: 0.1s sleep
# ---------------------------------------------------------------------------

def test_fetch_range_reads_cache_once_per_month(monkeypatch, tmp_cache_dir):
    """fetch_range must read each month's cache at most once (P3).

    Previously `fetch_range` called `_month_requires_network` (which reads
    `cache_get_month`) AND `fetch_month` (which reads `cache_get_month` again
    on a cache hit) -> two reads per month. The `_fetch_month_with_flag`
    helper does the lookup once. We pre-populate a fully cached month, spy on
    `cache_get_month`, and assert exactly one read for that month.
    """
    y, m = 2024, 1
    for d in range(1, 21):  # los 15 días de la ventana quedan cacheados
        core.cache_put(f"{y:04d}-{m:02d}-{d:02d}", 3.70, 3.75)

    calls: list = []
    real_cache_get_month = core.cache_get_month

    def spy_cgmonth(year, month):
        calls.append((year, month))
        return real_cache_get_month(year, month)

    monkeypatch.setattr(core, "cache_get_month", spy_cgmonth)
    core.fetch_range(date(2024, 1, 1), date(2024, 1, 15))

    jan_calls = [c for c in calls if c == (2024, 1)]
    assert len(jan_calls) == 1, (
        f"fetch_range must read each month's cache once, got {len(jan_calls)} "
        f"reads for Jan 2024: {calls}"
    )


def test_fetch_range_sleeps_0_1s_on_network_month(monkeypatch, tmp_cache_dir):
    """A network-served month must sleep 0.1s (not 0.3s) in fetch_range (P4).

    Además del trailing de 0.1s por mes con red, el fetch día a día espera
    `DAY_REQUEST_DELAY` entre peticiones consecutivas (429-safe).
    """
    rows_data = [
        {"fecha": f"2024-01-{d:02d}", "compra": 3.70, "venta": 3.75}
        for d in range(1, 21)
    ]
    monkeypatch.setattr(core, "_get_with_retry", lambda params, **kw: rows_data)
    monkeypatch.setattr(core, "DAY_REQUEST_DELAY", 1.5)
    sleeps: list[float] = []
    monkeypatch.setattr(core.time, "sleep", lambda d: sleeps.append(d))

    core.fetch_range(date(2024, 1, 1), date(2024, 1, 15))

    assert sleeps[-1] == 0.1, (
        f"network month must sleep exactly 0.1s after the month, got {sleeps}"
    )
    assert sleeps.count(1.5) == 14, (
        f"15 días de red -> 14 esperas de pacing, got {sleeps}"
    )


def test_fetch_range_fetches_only_days_in_range(monkeypatch, tmp_cache_dir):
    """Un rango corto no debe pedir el mes completo a la red."""
    asked: list[str] = []

    def fake_get(params, **kw):
        asked.append(params["fecha"])
        return [{"fecha": params["fecha"], "compra": 3.70, "venta": 3.75}]

    monkeypatch.setattr(core, "_get_with_retry", fake_get)
    monkeypatch.setattr(core.time, "sleep", lambda _d: None)

    rows = core.fetch_range(date(2024, 1, 10), date(2024, 1, 12))

    assert asked == ["2024-01-10", "2024-01-11", "2024-01-12"], (
        f"sólo los 3 días del rango deben ir a la red, got {asked}"
    )
    assert [r["fecha"] for r in rows] == ["2024-01-10", "2024-01-11", "2024-01-12"]


# ---------------------------------------------------------------------------
# Validator wiring in fetch_range / fetch_month
# ---------------------------------------------------------------------------

def test_fetch_range_raises_fetcherror_on_invalid_range():
    """fetch_range must raise FetchError(kind='input') when validators reject."""
    today = date.today()
    with pytest.raises(core.FetchError) as exc_info:
        core.fetch_range(today, today - timedelta(days=1))  # start > end
    assert exc_info.value.kind == "input"


def test_fetch_month_raises_fetcherror_on_invalid_month():
    """fetch_month must raise FetchError(kind='input') when validators reject."""
    with pytest.raises(core.FetchError) as exc_info:
        core.fetch_month(year=1900, month=1)  # year below MIN_YEAR
    assert exc_info.value.kind == "input"


# ---------------------------------------------------------------------------
# load_state non-dict guard (B4)
# ---------------------------------------------------------------------------


def test_load_state_non_dict_array_returns_default(tmp_cache_dir):
    """state.json containing a JSON array must yield dict(DEFAULT_STATE)."""
    _, state_file = tmp_cache_dir
    state_file.write_text("[1, 2, 3]", encoding="utf-8")
    state = core.load_state()
    assert state == dict(core.DEFAULT_STATE), (
        f"non-dict payload must return DEFAULT_STATE, got {state!r}"
    )


def test_load_state_non_dict_null_returns_default(tmp_cache_dir):
    """state.json containing `null` must yield dict(DEFAULT_STATE)."""
    _, state_file = tmp_cache_dir
    state_file.write_text("null", encoding="utf-8")
    state = core.load_state()
    assert state == dict(core.DEFAULT_STATE), (
        f"null payload must return DEFAULT_STATE, got {state!r}"
    )


def test_load_state_non_dict_scalar_returns_default(tmp_cache_dir):
    """state.json containing a scalar (number) must yield dict(DEFAULT_STATE)."""
    _, state_file = tmp_cache_dir
    state_file.write_text("5", encoding="utf-8")
    state = core.load_state()
    assert state == dict(core.DEFAULT_STATE), (
        f"scalar payload must return DEFAULT_STATE, got {state!r}"
    )


# ---------------------------------------------------------------------------
# MIN_YEAR single source of truth (B8)
# ---------------------------------------------------------------------------


def test_min_year_exported_from_validators():
    """MIN_YEAR is canonically defined in core.validators and re-exported
    from core (fix-data-layer-bugs D4). We verify the binding by inspecting
    the `core` module source: there MUST NOT be a second `MIN_YEAR = ...`
    assignment in `core/__init__.py`, only the re-export import. The
    `import core` line in this test file already exercises `from core
    import MIN_YEAR` via the module-level `import core` statement; we just
    assert the value matches the canonical validators.MIN_YEAR.
    """
    from pathlib import Path

    import core.validators as cv

    assert hasattr(core, "MIN_YEAR"), "core.MIN_YEAR must remain a public re-export"
    assert core.MIN_YEAR == cv.MIN_YEAR, (
        f"core.MIN_YEAR must equal validators.MIN_YEAR; "
        f"got core.MIN_YEAR={core.MIN_YEAR!r}, cv.MIN_YEAR={cv.MIN_YEAR!r}"
    )

    # Guard against a regression: the duplicate definition in
    # core/__init__.py MUST be gone. We assert by searching the file
    # for a top-level assignment of MIN_YEAR (any line that starts with
    # `MIN_YEAR =` after stripping leading whitespace).
    init_src = Path(__file__).resolve().parent.parent.joinpath(
        "core", "__init__.py"
    ).read_text(encoding="utf-8")
    offender_lines = [
        ln for ln in init_src.splitlines()
        if ln.lstrip().startswith("MIN_YEAR ") and "=" in ln
        and not ln.lstrip().startswith("#")
    ]
    assert offender_lines == [], (
        "core/__init__.py must not redefine MIN_YEAR (single source = "
        f"core/validators.py); offending line(s): {offender_lines!r}"
    )


# ---------------------------------------------------------------------------
# MAX_YEAR → max_year() dynamism (B9)
# ---------------------------------------------------------------------------


def test_max_year_is_dynamic():
    """`core.max_year()` must return today's year (B9 / fix-data-layer-bugs D3).

    Replaces the import-time module constant `core.MAX_YEAR` (which went
    stale across midnight on Dec 31) with a function computed on every
    call.
    """
    assert callable(core.max_year), "core.max_year must be a callable"
    assert core.max_year() == date.today().year, (
        f"core.max_year() must return date.today().year; "
        f"got {core.max_year()!r}, expected {date.today().year!r}"
    )


def test_max_year_no_module_constant():
    """`core.MAX_YEAR` (the old import-time constant) MUST be removed."""
    assert not hasattr(core, "MAX_YEAR"), (
        "core.MAX_YEAR must be removed (replaced by core.max_year()); "
        "any external `from core import MAX_YEAR` consumer was a single "
        "in-repo user (app.py) updated in the same change."
    )


# ---------------------------------------------------------------------------
# B5 — DEFAULT_STATE geometry matches the minsize floor (fix-gui-lifecycle-bugs)
# ---------------------------------------------------------------------------


def test_default_state_geometry_is_850x600():
    """`core.DEFAULT_STATE["geometry"]` SHALL equal the `minsize` floor
    (`850x600`) so a first launch with no `state.json` is self-consistent
    with the runtime TclError fallback and the persisted geometry is not
    stale (fix-gui-lifecycle-bugs B5, app-startup-and-imports delta)."""
    assert core.DEFAULT_STATE["geometry"] == "850x600", (
        f"DEFAULT_STATE geometry must equal the minsize floor 850x600; "
        f"got {core.DEFAULT_STATE['geometry']!r}"
    )


# ---------------------------------------------------------------------------
# B7 — MAX_RANGE_DAYS single source of truth (re-export from core)
# ---------------------------------------------------------------------------


def test_max_range_days_reexported_from_core():
    """`MAX_RANGE_DAYS` is canonically defined in `core.validators` and SHALL
    be re-exported from `core` (fix-gui-lifecycle-bugs D3, input-validation
    delta). Single source of truth — `core/__init__.py` MUST NOT redefine it,
    only re-export it, mirroring the `MIN_YEAR` pattern from Change A."""
    from pathlib import Path

    import core.validators as cv

    assert hasattr(core, "MAX_RANGE_DAYS"), (
        "core.MAX_RANGE_DAYS must be re-exported from core.validators"
    )
    assert core.MAX_RANGE_DAYS == 730, (
        f"core.MAX_RANGE_DAYS must equal 730 (~2 years); "
        f"got {core.MAX_RANGE_DAYS!r}"
    )
    assert core.MAX_RANGE_DAYS == cv.MAX_RANGE_DAYS, (
        f"core.MAX_RANGE_DAYS must equal validators.MAX_RANGE_DAYS; "
        f"got core.MAX_RANGE_DAYS={core.MAX_RANGE_DAYS!r}, "
        f"cv.MAX_RANGE_DAYS={cv.MAX_RANGE_DAYS!r}"
    )

    # Guard against a regression: core/__init__.py MUST NOT contain a
    # second `MAX_RANGE_DAYS = ...` assignment — only the re-export import.
    # (A `MAX_RANGE_DAYS =` line starts with the name then `=`; the
    # `from .validators import MAX_RANGE_DAYS, ...` re-export starts with
    # `from`, so it is correctly excluded.)
    init_src = Path(__file__).resolve().parent.parent.joinpath(
        "core", "__init__.py"
    ).read_text(encoding="utf-8")
    offender_lines = [
        ln for ln in init_src.splitlines()
        if ln.lstrip().startswith("MAX_RANGE_DAYS ") and "=" in ln
        and not ln.lstrip().startswith("#")
    ]
    assert offender_lines == [], (
        "core/__init__.py must not redefine MAX_RANGE_DAYS (single source = "
        f"core/validators.py); offending line(s): {offender_lines!r}"
    )


# ---------------------------------------------------------------------------
# Q2 — FetchError kind validation at construction (quality-lint-and-hardening)
# ---------------------------------------------------------------------------


def test_fetch_error_invalid_kind_raises_valueerror():
    """Constructing a FetchError with a kind not in `FetchError.kinds` MUST
    raise `ValueError` (not `FetchError`) before any instance attribute is set
    or `super().__init__` is called (data-fetch delta, Q2 / D2).
    """
    with pytest.raises(ValueError, match="Invalid FetchError kind"):
        core.FetchError("bogus")


def test_fetch_error_valid_kind_constructs_normally():
    """Triangulation: a valid kind must still construct and populate
    `.kind` / `.status` and carry the message through `str(exc)` (data-fetch
    delta "Valid kinds still construct normally"). Guards against a Fake-It
    that rejects every kind.
    """
    exc = core.FetchError(kind="network", message="down", status=None)
    assert exc.kind == "network"
    assert exc.status is None
    assert str(exc) == "down"


# ---------------------------------------------------------------------------
# Q8 — centralized `__version__` (quality-lint-and-hardening)
# ---------------------------------------------------------------------------


def test_core_has_version():
    """`core.__version__` SHALL be the single source of truth for the app
    version (app-startup-and-imports delta, Q8 / D4)."""
    assert core.__version__ == "1.0.0"


# ---------------------------------------------------------------------------
# Token de la API v2 (config.json + SUNAT_TC_TOKEN) y shapes de normalización
# ---------------------------------------------------------------------------


def test_token_roundtrip_in_config_file(tmp_cache_dir):
    """save_token/load_token persisten en config.json (y "" lo borra)."""
    assert core.load_token() is None, "sin config.json no hay token"
    assert core.save_token("sk_test.abc") is True
    assert core.load_token() == "sk_test.abc"
    assert core.save_token("") is True
    assert core.load_token() is None, "un token vacío borra la entrada"


def test_get_api_token_env_overrides_file(monkeypatch, tmp_cache_dir):
    """SUNAT_TC_TOKEN (entorno) tiene prioridad sobre config.json."""
    core.save_token("from-file")
    monkeypatch.setenv("SUNAT_TC_TOKEN", "from-env")
    assert core.get_api_token() == "from-env"
    monkeypatch.delenv("SUNAT_TC_TOKEN")
    assert core.get_api_token() == "from-file"


def test_load_token_corrupt_config_returns_none(tmp_cache_dir):
    """Un config.json inválido no debe romper la app: devuelve None."""
    core.CONFIG_FILE.write_text("{no es json", encoding="utf-8")
    assert core.load_token() is None


def test_normalize_v2_decolecta_shape():
    """Shape v2 decolecta: date/buy_price/sell_price (strings) se normaliza."""
    item = {"date": "2026-09-15", "buy_price": "3.373", "sell_price": "3.383"}
    assert core._normalize_item(item) == {
        "fecha": "2026-09-15",
        "compra": 3.373,
        "venta": 3.383,
    }


def test_normalize_v2_apisnet_shape():
    """Shape v2 api.apis.net.pe: fecha/precioCompra/precioVenta se normaliza."""
    item = {"fecha": "2026-09-15", "precioCompra": 3.373, "precioVenta": 3.383}
    assert core._normalize_item(item) == {
        "fecha": "2026-09-15",
        "compra": 3.373,
        "venta": 3.383,
    }


def test_fetch_month_uses_v2_single_request_with_token(monkeypatch, tmp_cache_dir):
    """Con token, el mes llega en UNA petición v2 (sin bucle día a día)."""
    monkeypatch.setenv("SUNAT_TC_TOKEN", "sk_test")
    calls: list = []

    def fake_v2(params, token, **kw):
        calls.append((params, token))
        return [
            {"date": f"2024-01-{d:02d}", "buy_price": "3.70", "sell_price": "3.75"}
            for d in range(1, 32)
        ]

    monkeypatch.setattr(core, "_get_v2_with_retry", fake_v2)
    monkeypatch.setattr(
        core,
        "_get_with_retry",
        lambda *a, **k: pytest.fail("con token no debe usarse la API v1"),
    )

    rows = core.fetch_month(2024, 1)

    assert calls == [({"year": 2024, "month": 1}, "sk_test")], (
        f"debe ser 1 petición v2 con month/year, got {calls}"
    )
    assert len(rows) == 31
    assert rows[0] == {"fecha": "2024-01-01", "compra": 3.70, "venta": 3.75}


def test_fetch_month_v2_discards_days_outside_window(monkeypatch, tmp_cache_dir):
    """v2: días fuera de la ventana (otro mes, futuro) se descartan."""
    monkeypatch.setenv("SUNAT_TC_TOKEN", "sk_test")
    monkeypatch.setattr(
        core,
        "_get_v2_with_retry",
        lambda params, token, **kw: [
            {"date": "2023-12-31", "buy_price": 3.6, "sell_price": 3.65},
            {"date": "2024-01-05", "buy_price": 3.7, "sell_price": 3.75},
            {"date": "2024-02-01", "buy_price": 3.8, "sell_price": 3.85},
        ],
    )

    rows = core.fetch_month(2024, 1)

    assert [r["fecha"] for r in rows] == ["2024-01-05"]


def test_fetch_month_v2_cache_hit_skips_network(monkeypatch, tmp_cache_dir):
    """v2: ventana completamente cacheada -> sin red y sin pacing."""
    for d in range(1, 32):
        core.cache_put(f"2024-01-{d:02d}", 3.70, 3.75)
    monkeypatch.setenv("SUNAT_TC_TOKEN", "sk_test")
    monkeypatch.setattr(
        core,
        "_get_v2_with_retry",
        lambda *a, **k: pytest.fail("ventana cacheada no debe ir a la red"),
    )
    sleeps: list = []
    monkeypatch.setattr(core.time, "sleep", lambda d: sleeps.append(d))

    rows = core.fetch_month(2024, 1)

    assert len(rows) == 31, "la ventana completa se sirve del caché"
    assert sleeps == [], "un cache-hit no debe dormir"


def test_fetch_month_v2_auth_error(monkeypatch, tmp_cache_dir):
    """401/403 de la v2 -> FetchError(kind='auth') sin reintentos."""
    monkeypatch.setenv("SUNAT_TC_TOKEN", "sk_bad")
    with requests_mock.Mocker() as m:
        m.get(
            core.API_V2_BASE,
            status_code=401,
            json={"error": "Apikey Required"},
        )
        with pytest.raises(core.FetchError) as exc_info:
            core.fetch_month(2024, 1)
    assert exc_info.value.kind == "auth"
    assert exc_info.value.status == 401


def test_check_token_verdicts(tmp_cache_dir):
    """check_token: True aceptado / False rechazado / None no verificable."""
    with requests_mock.Mocker() as m:
        m.get(
            core.API_V2_BASE,
            status_code=200,
            json={"date": "2026-10-09", "buy_price": 3.4, "sell_price": 3.5},
        )
        assert core.check_token("sk_ok") is True

        m.get(core.API_V2_BASE, status_code=401, json={"error": "bad token"})
        assert core.check_token("sk_bad") is False

        m.get(core.API_V2_BASE, exc=requests.exceptions.ConnectionError)
        assert core.check_token("sk_offline") is None


def test_fetch_day_ignores_token_and_uses_v1(monkeypatch, tmp_cache_dir):
    """El día suelto sigue por la v1 pública aunque haya token (igual de rápido)."""
    monkeypatch.setenv("SUNAT_TC_TOKEN", "sk_test")
    asked: list = []

    def fake_v1(params, **kw):
        asked.append(params)
        return [{"fecha": params["fecha"], "compra": 3.7, "venta": 3.8}]

    monkeypatch.setattr(core, "_get_with_retry", fake_v1)
    monkeypatch.setattr(
        core,
        "_get_v2_with_retry",
        lambda *a, **k: pytest.fail("fetch_day no debe usar la v2"),
    )

    rows = core.fetch_day("2024-01-15")

    assert asked == [{"fecha": "2024-01-15"}]
    assert rows == [{"fecha": "2024-01-15", "compra": 3.7, "venta": 3.8}]
