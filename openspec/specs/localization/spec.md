# Localization Specification

## Purpose

Defines the user-facing language used in status messages, dialogs, and
CLI stderr text, and locks the month-name vocabulary to Spanish so the
UI is consistent across modules. Aligns with the project convention:
source-code identifiers in English, user-visible strings in Spanish.
References: Engram `#1879` (finding #15), Engram `#1882` (Theme C,
cross-cutting concern #5), cached product decision 4A.

## Requirements

### Requirement: `MONTHS_ES` constant for Spanish month labels

`core.MONTHS_ES` SHALL be a 13-element sequence (index 0 unused,
indices 1..12) of Spanish month names (`["", "Enero", "Febrero", …,
"Diciembre"]`). `core.MONTHS_ABBR_ES` SHALL be the abbreviated
counterpart (`["", "Ene", "Feb", …, "Dic"]`). Both are imported from
`core` by every call site that needs them.

#### Scenario: 1-based lookup returns Spanish
- GIVEN `MONTHS_ES` and `MONTHS_ABBR_ES`
- WHEN an index in `[1, 12]` is used
- THEN the value is the corresponding Spanish name, not
  `calendar.month_name[m]` or `calendar.month_abbr[m]`

### Requirement: `fetch_range` progress uses Spanish abbreviations

The progress message emitted by `fetch_range` for each month SHALL be
built from `MONTHS_ABBR_ES[m]` and the four-digit year (e.g.
`"Consultando Ene 2025 (1/12)…"`). `calendar.month_abbr` SHALL NOT
appear on this code path.

#### Scenario: Spanish abbreviation in CLI/GUI range progress
- GIVEN `fetch_range` walks the months of 2025
- WHEN each month's `on_progress` callback fires
- THEN the text contains `"Ene"`, `"Feb"`, etc. (not `"Jan"`,
  `"Feb"`)

### Requirement: GUI month-fetch progress uses Spanish month names

`SunatTCApp._fetch_worker` SHALL build its `"Consultando [month]
[year]…"` status string from `MONTHS_ES[params['month']]`.
`calendar.month_name` SHALL NOT appear on this code path.

#### Scenario: Spanish full name in GUI progress
- GIVEN a month query for `year=2025, month=1`
- WHEN the worker reports progress
- THEN the status text contains `"Enero"`, not `"January"`

### Requirement: All user-facing strings are in Spanish

Every string a user sees — GUI status bar, `messagebox`, CLI stderr —
SHALL be in Spanish. Internal log messages and exception class names
SHALL be in English (programmer convention).

#### Scenario: Status text is Spanish
- GIVEN the GUI displays a status such as "Caché borrado.", "Listo",
  or "Consultando SUNAT…"
- WHEN a user reads it
- THEN the string is in Spanish

#### Scenario: Exception class names are English
- GIVEN the data layer raises a typed error such as `FetchError`
- WHEN a developer inspects it
- THEN the class name is in English (`FetchError`, not
  `ErrorDeConsulta`)

## Out of Scope

- A full i18n framework (gettext, .po files). The app ships Spanish-only.
- Translating identifiers, comments, or docstrings to Spanish.
- New UI strings outside the scope of the 15 fixes (tooltips, menus,
  etc.).
