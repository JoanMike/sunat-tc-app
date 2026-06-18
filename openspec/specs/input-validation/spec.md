# Input Validation Specification

## Purpose

Defines the shared date-validation contract used by both the CLI
(`--range`, `--month`) and the GUI (range `DateEntry`, month/year
spinboxes), so that both surfaces reject the same invalid inputs with the
same Spanish error messages and the rules cannot drift apart. References:
Engram `#1879` (findings #5, #6), Engram `#1882` (Theme B, cross-cutting
concern #1).

## Requirements

### Requirement: `validate_range(start, end)` shared helper

`core.validate_range(start, end)` SHALL return `tuple[date, date]` on
success and `str` (Spanish error message) on any validation failure. It
SHALL reject: malformed `date` arguments, `start > end`, `end >
date.today()`, and ranges spanning more than 730 days.

#### Scenario: End date in the future
- GIVEN `start = date(2025, 1, 1)` and `end = date(2099, 1, 1)`
- WHEN `core.validate_range(start, end)` is called
- THEN it returns a Spanish `str` stating that the end date cannot be in
  the future

#### Scenario: Span exceeds 730 days
- GIVEN `start = date(2023, 1, 1)` and `end = date(2025, 6, 1)`
- WHEN `core.validate_range(start, end)` is called
- THEN it returns a Spanish `str` stating the 730-day maximum

#### Scenario: Valid range
- GIVEN `start` and `end` that satisfy every rule
- WHEN `core.validate_range(start, end)` is called
- THEN it returns the `(start, end)` tuple

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

### Requirement: CLI and GUI use the shared validators

The CLI's `--range` and `--month` parsing paths SHALL call
`core.validate_range` and `core.validate_month` instead of duplicating the
rules inline. The GUI's `_validate_inputs` SHALL likewise call the shared
helpers. Drift between the two surfaces is forbidden.

The `MAX_RANGE_DAYS` constant SHALL be canonically defined in
`core.validators` and re-exported from `core` (single source of truth — no
duplicate definition in `core/__init__.py`). The GUI's `_validate_inputs`
range-cap comparison and its Spanish error message SHALL use `MAX_RANGE_DAYS`
(via the `core` re-export), not a hardcoded numeric literal, so the GUI range
cap and `core.validate_range` can never drift apart.

(Previously: the GUI `_validate_inputs` inlined the literal `730` in both the
comparison and the error f-string; `MAX_RANGE_DAYS` was not re-exported from
`core`.)

#### Scenario: CLI rejects future end-date
- GIVEN the user runs `python app.py --range 2025-01-01:2099-01-01`
- WHEN the CLI parses the arguments
- THEN it exits with code `2`, prints a Spanish error to stderr, and never
  calls `fetch_range`

#### Scenario: GUI rejects out-of-range year
- GIVEN the GUI year spinbox holds a year outside `[MIN_YEAR, max_year()]`
- WHEN the user clicks "Consultar"
- THEN a Spanish `messagebox.showwarning` is shown and no worker thread is
  started

#### Scenario: GUI range cap uses the canonical `MAX_RANGE_DAYS`
- GIVEN `core.MAX_RANGE_DAYS` is the canonical range cap
- WHEN the GUI `_validate_inputs` validates a range whose span exceeds the cap
- THEN the comparison uses `core.MAX_RANGE_DAYS` (not a hardcoded literal)
- AND the Spanish error message interpolates `MAX_RANGE_DAYS` so the number
  always matches the actual cap

## Out of Scope

- The exact Spanish error wording (design concern).
- New query modes such as quarter or year-to-date.
- Server-side or API-side validation.
