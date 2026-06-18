# Delta for data-fetch

> Delta spec for `fix-data-layer-bugs`.
> Main spec: `openspec/specs/data-fetch/spec.md`.

## ADDED Requirements

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

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

## RENAMED Requirements

None.
