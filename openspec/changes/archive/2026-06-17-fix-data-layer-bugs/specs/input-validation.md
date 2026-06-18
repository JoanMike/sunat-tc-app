# Delta for input-validation

> Delta spec for `fix-data-layer-bugs`.
> Main spec: `openspec/specs/input-validation/spec.md`.

## ADDED Requirements

None.

## MODIFIED Requirements

### Requirement: `validate_month(year, month)` shared helper

`core.validate_month(year, month)` SHALL return `tuple[int, int]` on
success and `str` (Spanish error message) on any validation failure. It
SHALL reject: non-integer arguments, `month` outside `[1, 12]`, and
`year` outside `[MIN_YEAR, max_year()]`.

The `MIN_YEAR` constant SHALL be canonically defined in `core.validators`
and re-exported from `core` (single source of truth — no duplicate
definition in `core/__init__.py`). `max_year()` SHALL be a zero-argument
callable in `core` that returns `date.today().year` and is re-evaluated
on every invocation, so long-running processes do not see a stale upper
bound across midnight on December 31. The module-level `MAX_YEAR`
constant in `core` SHALL be removed.

(Previously: `MAX_YEAR` was a `core` module constant evaluated once at
import time; `MIN_YEAR` was defined in both `core/__init__.py` and
`core/validators.py`.)

#### Scenario: Year below `MIN_YEAR`

- GIVEN `year = 1900` and `month = 1`
- WHEN `core.validate_month(1900, 1)` is called
- THEN it returns a Spanish `str` stating that the year is below the
  allowed minimum

#### Scenario: Valid month

- GIVEN a year in `[MIN_YEAR, max_year()]` and a month in `[1, 12]`
- WHEN `core.validate_month(year, month)` is called
- THEN it returns the `(year, month)` tuple

## REMOVED Requirements

None.

## RENAMED Requirements

None.
