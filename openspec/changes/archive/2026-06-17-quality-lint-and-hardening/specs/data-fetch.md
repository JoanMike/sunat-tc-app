# Spec Delta: data-fetch (quality-lint-and-hardening)

> Modifies the typed `FetchError` requirement from Change A to add kind
> validation at construction time. References: exploration Q2; Engram
> `sdd/quality-lint-and-hardening/explore` (#1969).

## MODIFIED Requirements

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
documentary. The production `_GENERIC_FALLBACK` in `format_fetch_error` is
retained as defense-in-depth for paths that bypass `__init__`, e.g.
reconstruction via `__new__` or pickle.)

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

## Out of Scope

- The exact retry/backoff schedule (design concern).
- A pluggable transport layer; `requests` is the fixed HTTP client.
- Validating `status` ranges against `kind` (e.g. `http_4xx` implying a 4xx
  status) — only `kind` membership is enforced in this change.
