# Delta for gui-worker-lifecycle

> Delta spec for `fix-data-layer-bugs`.
> Main spec: `openspec/specs/gui-worker-lifecycle/spec.md`.

## ADDED Requirements

### Requirement: GUI fetch worker routes `FetchError` through shared core messages

`SunatTCApp._fetch_worker` SHALL catch `FetchError` BEFORE the generic
`except Exception` and call `core.format_fetch_error(exc)` to produce the
status-bar message passed to `on_done`. The GUI SHALL NOT fall back to
`str(exc)` (English-y technical text such as `"HTTP 503"`) for `FetchError`
exceptions — Spanish GUI users MUST see the mapped Spanish message from
`core.messages`. The generic `except Exception` branch is kept as a
safety net for non-`FetchError` exceptions and continues to use its
current `"Error inesperado: {exc}"` text.

#### Scenario: `FetchError` produces a Spanish status message

- GIVEN the worker raises `FetchError(kind="http_5xx")`
- WHEN `_on_fetch_done` runs
- THEN `on_done([], core.format_fetch_error(exc))` is called
- AND the status bar shows the mapped Spanish message
- AND `str(exc)` is NOT used as the user-visible text

#### Scenario: non-`FetchError` still uses the generic fallback

- GIVEN the worker raises an exception that is NOT a `FetchError`
  (e.g. `KeyError`, `RuntimeError`)
- WHEN `_on_fetch_done` runs
- THEN the generic `except Exception` branch handles it
- AND the `FetchError` branch does not match

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

## RENAMED Requirements

None.
