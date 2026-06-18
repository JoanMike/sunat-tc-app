# Delta for input-validation

> Delta spec for `fix-gui-lifecycle-bugs`.
> Main spec: `openspec/specs/input-validation/spec.md`.

## ADDED Requirements

None.

## MODIFIED Requirements

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

## REMOVED Requirements

None.

## RENAMED Requirements

None.
