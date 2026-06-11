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
`"http_4xx"`, `"http_5xx"`, or `"parse"`. The function SHALL NOT collapse any
of these failure modes to a silent `[]`. A 404 or 204 response (legitimately
"no data for this date") is not a failure and SHALL continue to return `[]`.

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

### Requirement: Cache-hit short-circuit in `fetch_range`

`fetch_range` SHALL NOT call `time.sleep` between months when every month in
the range is fully served from the local cache. The 0.3-second politeness
sleep SHALL only run when the month required a network call.

#### Scenario: Range fully cached
- GIVEN every month in `[start, end]` already has at least
  `MIN_DAYS_FOR_CACHED_MONTH` entries in the cache
- WHEN `fetch_range(start, end)` is called
- THEN the returned rows come entirely from cache and `time.sleep` is not
  called

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

## Out of Scope

- The exact retry/backoff schedule (design concern).
- A pluggable transport layer; `requests` is the fixed HTTP client.
- Cache invalidation policies beyond the existing "today always re-fetches"
  rule.
- How CLI/GUI callers react to `FetchError` (covered by `input-validation`
  and `gui-worker-lifecycle`).
