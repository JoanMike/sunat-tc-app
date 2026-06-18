# Delta for localization

> Delta spec for `fix-data-layer-bugs`.
> Main spec: `openspec/specs/localization/spec.md`.

## ADDED Requirements

### Requirement: `core.format_fetch_error` is the single Spanish mapper for `FetchError`

`core.format_fetch_error(exc)` SHALL be the single source of truth for
mapping a `FetchError` (any `kind`) to a Spanish user-facing message.
The mapping table (`_FETCH_ERROR_MESSAGES_ES`) SHALL live in
`core.messages` and be re-exported from `core`. Both the CLI and the
GUI SHALL call `core.format_fetch_error(exc)` — no surface SHALL
duplicate the mapping table or fall back to `str(exc)` for `FetchError`.

The mapping table SHALL cover every `FetchError.kind` value the data
layer can raise: `"network"`, `"http_4xx"`, `"http_5xx"`, `"parse"`,
`"rate_limit"`, and `"input"`. Adding a new `kind` without extending
the table is a spec violation (it would surface as English debug text).

#### Scenario: CLI surfaces a Spanish rate-limit message

- GIVEN a `FetchError(kind="rate_limit", status=429)` propagates from
  `_get_with_retry`
- WHEN the CLI formats the error
- THEN `core.format_fetch_error(exc)` returns a Spanish message about
  rate limiting / waiting a moment
- AND the CLI writes that string to stderr; no `str(exc)` fallback runs

#### Scenario: GUI surfaces a Spanish fetch-error message

- GIVEN a `FetchError(kind="http_5xx")` propagates from `_fetch_worker`
- WHEN `_on_fetch_done` runs
- THEN `core.format_fetch_error(exc)` returns a Spanish message about
  SUNAT being unavailable
- AND the GUI status bar shows that string; no `str(exc)` fallback runs

#### Scenario: every FetchError.kind has a Spanish mapping

- GIVEN the set of `FetchError.kind` values:
  `{"network", "http_4xx", "http_5xx", "parse", "rate_limit", "input"}`
- WHEN `core.format_fetch_error` is called with one of each
- THEN every call returns a non-empty Spanish string
- AND no kind falls through to a default / `str(exc)` branch

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

## RENAMED Requirements

None.
