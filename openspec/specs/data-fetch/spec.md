# Data Fetch Specification

## Purpose

Defines the data-layer contract for retrieving SUNAT exchange rates over HTTP,
normalizing API payloads, serving cached results, and reporting fetch failures.
This is the single contract shared by the CLI and the GUI; both surfaces MUST
consume it the same way. References: Engram `#1879` (findings #2, #3, #8, #10),
Engram `#1882` (Theme A), Engram `#1883`.

## Requirements

### Requirement: Typed `FetchError` from `_get_with_retry`

`_get_with_retry` SHALL signal persistent fetch failures by raising a
`FetchError` exception whose `kind` attribute is one of `"network"`,
`"http_4xx"`, `"http_5xx"`, `"parse"`, `"rate_limit"`, or `"input"`.
`_get_with_retry` SHALL NOT collapse any fetch failure mode to a silent `[]`.
A 404 or 204 response (legitimately "no data for this date") is not a failure
and SHALL continue to return `[]`.

`FetchError.__init__` SHALL validate that the supplied `kind` is a member of the
class-level `kinds` tuple. If `kind` is not one of the allowed values,
`__init__` SHALL raise `ValueError` (with a message naming the invalid kind and
the allowed set) BEFORE setting any instance attribute or calling
`super().__init__`. A valid `kind` SHALL construct normally and populate
`self.kind` and `self.status` as before.

`"input"` is reserved for validation failures raised by higher-level fetch
helpers before an HTTP call. `"rate_limit"` is reserved for API throttling
semantics so CLI and GUI callers can map it explicitly when that branch is
introduced.

(The class-level `kinds` tuple is now enforced at construction, not merely
documentary. The production fallback in `format_fetch_error` is retained as
defense-in-depth for paths that bypass `__init__`, e.g. reconstruction via
`__new__` or pickle.)

#### Scenario: 5xx after all retries
- GIVEN the API returns a retryable 5xx status for every attempt
- WHEN `_get_with_retry(params)` is called
- THEN it raises `FetchError(kind="http_5xx")` instead of returning `[]`

#### Scenario: Network failure
- GIVEN `requests.get` raises `requests.RequestException` for every attempt
- WHEN `_get_with_retry(params)` is called
- THEN it raises `FetchError(kind="network")`

#### Scenario: 404 is not an error
- GIVEN the API returns 404 for a non-existent date
- WHEN `_get_with_retry(params)` is called
- THEN it returns `[]` (no exception)

#### Scenario: Invalid kind is rejected at construction
- GIVEN the `FetchError` class with its `kinds` tuple
- WHEN `FetchError("bogus")` is constructed
- THEN it raises `ValueError` (not `FetchError`) and no `FetchError` instance is
  returned to the caller

#### Scenario: Valid kinds still construct normally
- GIVEN the `FetchError` class with its `kinds` tuple
- WHEN `FetchError(kind="network", message="down", status=None)` is constructed
- THEN the instance's `.kind == "network"` and `.status is None` and
  `str(instance)` reflects the message

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

### Requirement: Numeric `0` preserved by `_normalize_item`

`_normalize_item` SHALL treat a numeric `0` for `compra` or `venta` as valid
data. The Python `or` operator SHALL NOT be used to chain fallback keys for
numeric fields, because `0` is falsy and would be discarded.

#### Scenario: `compra` is zero
- GIVEN the API payload `{"fecha": "2025-01-15", "compra": 0, "venta": 3.5}`
- WHEN `_normalize_item` is called
- THEN it returns `{"fecha": "2025-01-15", "compra": 0.0, "venta": 3.5}`
  (not `None`)

### Requirement: No filesystem side effects at `core.py` import

`core.py` SHALL NOT call `Path.mkdir`, `os.mkdir`, or any equivalent
filesystem mutation during module import. Directory creation SHALL be
deferred to a lazy `_ensure_app_data_dir()` helper invoked the first time a
cache function opens the database.

#### Scenario: Importing core does not create the app data dir
- GIVEN a clean process and a missing app data directory
- WHEN `import core` is executed
- THEN the directory is not created; it is created lazily on the first call
  to `cache_get`, `cache_put`, or another cache function

### Requirement: `FetchError(kind="rate_limit")` on 429 retry exhaustion

`_get_with_retry` SHALL raise `FetchError(kind="rate_limit")` (carrying the
HTTP `status=429`) when the API returns a 429 response for every retry
attempt. HTTP 429 SHALL remain in `RETRYABLE_STATUS` and SHALL still be
retried per the existing exponential-backoff schedule; only the terminal
`FetchError.kind` value changes from `"http_5xx"` to `"rate_limit"` after
retries are exhausted. This activates the `"rate_limit"` kind that the
typed-FetchError requirement reserves for API throttling.

#### Scenario: 429 after all retries
- GIVEN the API returns HTTP 429 for every retry attempt
- WHEN `_get_with_retry(params)` is called
- THEN it raises `FetchError(kind="rate_limit")` with `status=429`
- AND HTTP 429 is in `RETRYABLE_STATUS` (still retried, not raised on first contact)

#### Scenario: 5xx after all retries still raises `http_5xx`
- GIVEN the API returns a retryable 5xx status (not 429) for every attempt
- WHEN `_get_with_retry(params)` is called
- THEN it raises `FetchError(kind="http_5xx")` — not `rate_limit`

### Requirement: `load_state` rejects non-dict JSON payloads

`core.load_state` SHALL validate that the decoded JSON payload is a `dict`
before merging it with `DEFAULT_STATE`. If the decoded payload is not a
`dict` (e.g. the file contains `5`, `[1, 2, 3]`, `null`, or any JSON value
that is not a JSON object), `load_state` SHALL return `dict(DEFAULT_STATE)`
without raising. `TypeError` SHALL also be caught at the merge site as a
defensive safety net alongside the existing `OSError`,
`json.JSONDecodeError`, and `ValueError` cases.

`load_state` belongs to the data layer (it lives in `core`); this delta
puts the shape guard here because no dedicated state-persistence spec
exists and `data-fetch` is the closest existing home for core-layer
contracts.

#### Scenario: state.json contains a JSON array
- GIVEN `state.json` contains `[1, 2, 3]` (valid JSON, not a dict)
- WHEN `core.load_state()` is called
- THEN it returns `dict(DEFAULT_STATE)` and does not raise `TypeError`

#### Scenario: state.json contains a JSON null
- GIVEN `state.json` contains `null`
- WHEN `core.load_state()` is called
- THEN it returns `dict(DEFAULT_STATE)` and does not raise `TypeError`

### Requirement: `fetch_range` relies on `validate_range` for input validation

`fetch_range` SHALL NOT carry a defensive `if end < start: return []`
post-validate branch. Input validation (including the `start > end`
case) is the sole responsibility of `core.validate_range`, which is
invoked at the top of `fetch_range` and raises
`FetchError(kind="input")` on any invalid input. A subsequent
post-validate check is unreachable and SHALL be removed.

#### Scenario: inverted range raises from `validate_range`
- GIVEN `start > end`
- WHEN `fetch_range(start, end)` is called
- THEN `validate_range` raises `FetchError(kind="input")` before any
  downstream branch can execute (no `return []` short-circuit)

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

## Out of Scope

- The exact retry/backoff schedule (design concern).
- A pluggable transport layer; `requests` is the fixed HTTP client.
- Cache invalidation policies beyond the existing "today always re-fetches"
  rule.
- How CLI/GUI callers react to `FetchError` (covered by `input-validation`
  and `gui-worker-lifecycle`).
