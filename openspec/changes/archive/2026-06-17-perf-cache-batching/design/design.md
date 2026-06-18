# Design: perf-cache-batching (Change E)

## Technical Approach

Four local performance fixes in `core/__init__.py` (post-A, 479 lines), all
in the cache + fetch layer. No new modules, no API breaks. Strict TDD
RED-first; P3 and P4 ship in one commit because the `network_happened` flag
produced by the P3 helper is consumed by the P4 sleep. Single PR ~160 LoC.

## Files

| File | Action | Post-A lines | Change |
|------|--------|-------------|--------|
| `core/__init__.py` | Modify | 191-207, 264-287, 324-343, 346-364, 367-416, 419-430 | P1-P4 |
| `tests/test_core.py` | Modify (add tests) | after existing cache/fetch tests | New RED tests |

No other files. No GUI/CLI/docs touched.

## Architecture Decisions

### D1 (P1): `cache_put_many(rows)` as the single implementation; `cache_put` thin wrapper

**Choice**: `cache_put_many(rows: Iterable[tuple], source="apis.net.pe")` opens one connection, runs `executemany` with the existing `INSERT ... ON CONFLICT(fecha) DO UPDATE` upsert, commits once, closes. `fetched_at` computed once per batch. `cache_put(fecha, compra, venta, source)` becomes `cache_put_many([(fecha, compra, venta, source)])`.

**Alternatives**: (A) keep `cache_put` independent and add `cache_put_many` alongside — rejected, two INSERT SQL strings (DRY violation) and inconsistent `fetched_at`. Context-manager connection pool — overkill for a single-user desktop app.

**Rationale**: One SQL string (DRY), one connection for N rows (was N), consistent batch `fetched_at` matching "rows fetched together" semantics. Existing single-row `cache_put` tests pass unchanged.

**After** (`cache_put_many` body + wrapper):
```python
def cache_put_many(rows, source="apis.net.pe"):
    conn = _connect()
    try:
        fetched_at = datetime.now().isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO rates (fecha, compra, venta, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(fecha) DO UPDATE SET "
            "compra=excluded.compra, venta=excluded.venta, "
            "source=excluded.source, fetched_at=excluded.fetched_at",
            [(r[0], float(r[1]), float(r[2]), r[3] if len(r) > 3 else source, fetched_at)
             for r in rows],
        )
        conn.commit()
    finally:
        conn.close()

def cache_put(fecha, compra, venta, source="apis.net.pe"):
    cache_put_many([(fecha, compra, venta, source)])
```

`fetch_day` (341-342) / `fetch_month` (362-363): replace `for r in rows: cache_put(...)` with `cache_put_many([(r["fecha"], r["compra"], r["venta"]) for r in rows])`.

### D2 (P2): `CACHE_DB.exists()` guard before `sqlite3.connect`

**Choice**: In `_connect`, `if not CACHE_DB.exists(): <run DDL>` BEFORE `sqlite3.connect(CACHE_DB)`. DDL stays `CREATE TABLE/INDEX IF NOT EXISTS` (idempotent if two threads race on a missing file).

**Alternatives**: module-level `_schema_initialized` flag + lock — rejected, shared mutable state, flag goes stale if the DB file is deleted at runtime. Unconditional `CREATE TABLE IF NOT EXISTS` per call — the current behavior, rejected as the perf cost we are removing.

**Rationale**: `Path.exists()` is a cheap syscall; no shared state -> thread-safe by design; correctly re-runs DDL if the file is deleted between calls. Edge case: file exists but `rates` table missing (manual tampering) -> first `cache_*` call raises `OperationalError: no such table: rates`. Acceptable for a single-user single-process desktop app; documented known limitation, not in scope to heal.

**After** (`_connect` guard):
```python
def _connect() -> sqlite3.Connection:
    _ensure_app_data_dir()
    if not CACHE_DB.exists():          # NEW guard, before connect (which creates the file)
        conn_init = sqlite3.connect(CACHE_DB)
        conn_init.execute("CREATE TABLE IF NOT EXISTS rates (...)")
        conn_init.execute("CREATE INDEX IF NOT EXISTS idx_rates_fecha ON rates(fecha)")
        conn_init.commit()
        conn_init.close()
    return sqlite3.connect(CACHE_DB)   # no DDL on the hot path
```

### D3 (P3): private `_fetch_month_with_flag` helper; drop `_month_requires_network`

**Choice**: `_fetch_month_with_flag(year, month, use_cache) -> (list[dict], bool)` does the cache check ONCE (calls `cache_get_month`), applies `MIN_DAYS_FOR_CACHED_MONTH`, returns `(sorted_rows, False)` on a cache hit or `(rows, True)` on a network call. `fetch_range` calls it once per month and reads `network_happened` from the same call. Public `fetch_month(year, month, use_cache)` delegates and returns only the rows (contract preserved). `_month_requires_network` is deleted (grep confirms only `fetch_range` called it).

**Alternatives**: (a) change `fetch_month` to return `(rows, network_happened)` — rejected, breaks the public signature used by GUI/CLI/tests. (b) inline the cache check in `fetch_range` + a skip-cache internal fetch — rejected, duplicates the `MIN_DAYS_FOR_CACHED_MONTH` threshold logic in two places. (c) widen `_month_requires_network` to also return cached rows — rejected, splits cache-check logic between predicate and `fetch_range`.

**Rationale**: Single cache read per month; `network_happened` from the same call; threshold logic lives in ONE place; `fetch_month` contract unchanged. The regression test `test_fetch_range_cache_hit_skips_sleep` stays green: cache complete -> helper returns `(rows, False)` -> `fetch_range` skips sleep.

**After** (helper + `fetch_range` loop):
```python
def _fetch_month_with_flag(year, month, use_cache=True):
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
    cache_put_many([(r["fecha"], r["compra"], r["venta"]) for r in rows])
    return rows, True

def fetch_month(year, month, *, use_cache=True):
    rows, _ = _fetch_month_with_flag(year, month, use_cache)
    return rows
```
`fetch_range` loop body: `meses, network_happened = _fetch_month_with_flag(y, m, use_cache=use_cache)`; drop the `_month_requires_network` line (398).

### D4 (P4): `time.sleep(0.1)` + justification comment

**Choice**: `fetch_range` sleep line (412) becomes `time.sleep(0.1)` with a comment: `apis.net.pe` is a public free API; 0.1s remains polite; the existing exponential backoff in `_get_with_retry` already handles transient overload (429/5xx); worst case 2-year full miss drops 7.2s -> 2.4s.

**Rationale**: P3 and P4 are coupled via `network_happened` -> MUST ship in the same commit.

**After** (sleep line):
```python
        if network_happened:
            # apis.net.pe is a public free API; 0.1s stays polite. Backoff in
            # _get_with_retry already handles 429/5xx. 2yr full miss: 7.2s -> 2.4s.
            time.sleep(0.1)
```

## Data Flow

```
fetch_range --per month--> _fetch_month_with_flag --> cache_get_month (ONCE)
                              | hit?  return (rows, False) --> fetch_range skips sleep
                              | miss? _get_with_retry --> cache_put_many (ONE conn) --> return (rows, True)
                              +------------------------------------------------> fetch_range: time.sleep(0.1)
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit (P1) | `cache_put_many` one-connection + upsert + wrapper | monkeypatch `core._connect` to count calls; insert 20 rows -> assert 1 connection; insert duplicate fecha -> assert updated; `cache_put` round-trip via existing test |
| Unit (P1) | `fetch_month` batches writes | stub `_get_with_retry` to 20 rows; assert `cache_put_many` called once |
| Unit (P2) | DDL only when DB missing | pre-create `CACHE_DB`; spy `conn.execute` -> assert DDL not run on second call; first call on missing file runs DDL |
| Unit (P3) | single cache read per month | spy on `cache_get_month` in `fetch_range` -> assert at most once per month |
| Regression (P3) | cache hit skips sleep | `test_fetch_range_cache_hit_skips_sleep` stays green (existing) |
| Unit (P4) | sleep value 0.1s | cache miss -> monkeypatch `core.time` -> assert `sleep_calls == [0.1]` per network month |

RED test names (mapped to `tests/test_core.py`):
- P1: `test_cache_put_many_uses_one_connection`, `test_cache_put_many_upserts_on_conflict`, `test_cache_put_still_works_single_row`, `test_fetch_month_batches_cache_writes`
- P2: `test_connect_skips_ddl_when_db_exists`, `test_connect_runs_ddl_when_db_missing`
- P3: `test_fetch_range_reads_cache_once_per_month` (regression: `test_fetch_range_cache_hit_skips_sleep` stays green)
- P4: `test_fetch_range_sleeps_0_1s_on_network_month`

## Migration / Rollout

No migration required. Same schema, same `ON CONFLICT` upsert semantics; the DB file is untouched by the change. Rollback: `git revert` of the single PR.

## Open Questions

None. The 0.1s courtesy value is a documented judgment call (see P4); not a blocker.

## Out of Scope

- Changes A/B/D/F/G and any GUI, CLI, lint, docs, or new-bug work. Only `core/__init__.py` cache + fetch perf.
