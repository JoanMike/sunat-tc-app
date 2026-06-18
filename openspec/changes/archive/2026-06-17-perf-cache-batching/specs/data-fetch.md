# Delta for data-fetch

> Delta spec for `perf-cache-batching` (Change E).
> Main spec: `openspec/specs/data-fetch/spec.md`.

## ADDED Requirements

### Requirement: Batched cache writes via `cache_put_many`

`core` SHALL provide `cache_put_many(rows)` that inserts or updates N rows
with a single SQLite connection, a single `executemany` call, and a single
`commit`. The upsert semantics (`ON CONFLICT(fecha) DO UPDATE`) SHALL match
`cache_put`. `fetch_day` and `fetch_month` SHALL batch their per-row cache
writes through `cache_put_many`, calling it once per network response rather
than once per row. `cache_put(fecha, compra, venta, source)` SHALL be
retained as a thin wrapper that delegates to `cache_put_many`.

#### Scenario: fetch_month batches a multi-row response into one connection
- GIVEN a month network response yields 20 normalized rows
- WHEN `fetch_month(year, month)` writes them to the cache
- THEN `cache_put_many` is called exactly once and `_connect` is called
  exactly once for the write (not once per row)

#### Scenario: cache_put_many upserts on conflicting fecha
- GIVEN the cache already holds `2024-01-15` with old rates
- WHEN `cache_put_many([("2024-01-15", 3.80, 3.81, "apis.net.pe")])` is called
- THEN the existing row is updated in place and no duplicate primary key is inserted

#### Scenario: cache_put single-row wrapper still round-trips
- GIVEN an empty cache
- WHEN `cache_put("2024-01-15", 3.74, 3.75, source="test")` is called
- THEN `cache_get("2024-01-15")` returns that row with the given values

### Requirement: Schema DDL runs only when the database file is missing

`_connect` SHALL execute `CREATE TABLE` and `CREATE INDEX` only when
`CACHE_DB` does not exist. The `CACHE_DB.exists()` check SHALL run before
`sqlite3.connect` (which creates the file). Subsequent connections to an
existing database file SHALL skip the DDL. The check is stateless (no
module-level flag or lock) and therefore thread-safe.

#### Scenario: second connection skips DDL
- GIVEN the cache database file already exists with the `rates` table initialized
- WHEN `_connect()` is called a second time
- THEN `CREATE TABLE` and `CREATE INDEX` are not executed

#### Scenario: first connection on a missing file runs DDL
- GIVEN the cache database file does not exist
- WHEN `_connect()` is called for the first time
- THEN `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` run and the file is created

## MODIFIED Requirements

### Requirement: Cache-hit short-circuit in `fetch_range`

`fetch_range` SHALL read each month's cache at most once. A single private
`_fetch_month_with_flag(year, month, use_cache) -> (rows, network_happened)`
helper SHALL perform the cache lookup, apply the
`MIN_DAYS_FOR_CACHED_MONTH` threshold, and return the rows together with a
`network_happened` boolean. The separate `_month_requires_network`
pre-check SHALL be removed. The public `fetch_month` SHALL delegate to the
helper and return only the rows, preserving its existing return contract.

`fetch_range` SHALL NOT call `time.sleep` between months when every month in
the range is fully served from the local cache. The politeness sleep SHALL
run only when `network_happened` is true, with a value of `0.1` seconds
(previously `0.3`).

(Previously: `fetch_range` skipped `time.sleep(0.3)` on cache hits via a
separate `_month_requires_network` pre-check, causing a double cache read per
month.)

#### Scenario: Range fully cached
- GIVEN every month in `[start, end]` already has at least
  `MIN_DAYS_FOR_CACHED_MONTH` entries in the cache
- WHEN `fetch_range(start, end)` is called
- THEN the returned rows come entirely from cache and `time.sleep` is not
  called (RETAINED)

#### Scenario: Range with network months sleeps 0.1s each
- GIVEN a month in the range has fewer than `MIN_DAYS_FOR_CACHED_MONTH`
  cached entries and a network fetch succeeds
- WHEN `fetch_range(start, end)` is called
- THEN `time.sleep(0.1)` is called exactly once for that month (not `0.3`)

#### Scenario: Each month's cache is read at most once
- GIVEN a multi-month `fetch_range` invocation
- WHEN the range is processed
- THEN `cache_get_month` is called at most once per month in the range

## REMOVED Requirements

None.

## RENAMED Requirements

None.
