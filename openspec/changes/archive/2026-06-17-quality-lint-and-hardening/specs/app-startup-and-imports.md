# Spec Delta: app-startup-and-imports (quality-lint-and-hardening)

> Modifies the "Acerca de" requirement from Change F (which mandated a local
> `_APP_VERSION` placeholder) to source the version from the single source of
> truth `core.__version__`, and adds a `--version` CLI flag requirement.
> References: exploration Q8; Engram `sdd/quality-lint-and-hardening/explore` (#1969).

## MODIFIED Requirements

### Requirement: "Acerca de" dialog shows app version

`core` SHALL define a single `__version__` package attribute (a string) that is
the one source of truth for the application version. `app.py` SHALL import
`__version__` from `core` and SHALL NOT define a module-level `_APP_VERSION`
constant. The bottom bar SHALL include an "Acerca de…" `ttk.Button` that opens a
`messagebox.showinfo` dialog whose text MUST contain the value of
`core.__version__` and the data source "apis.net.pe". The dialog text SHALL be
Spanish.

(This supersedes the Change F requirement that mandated a temporary
`_APP_VERSION = "1.0.0"` placeholder. The placeholder is removed; the version is
now centralized in `core.__version__` per Q8.)

#### Scenario: About dialog displays version and source

- GIVEN the app is initialized with `core.__version__ = "1.0.0"`
- WHEN `_show_about()` is invoked (simulating the button click)
- THEN a `messagebox.showinfo` call is made whose text contains the value of
  `core.__version__` (e.g. `"1.0.0"`) and `"apis.net.pe"`

#### Scenario: app.py does not define a local version constant

- GIVEN `app.py` is imported
- WHEN `app.__dict__` is inspected
- THEN it does NOT contain the symbol `_APP_VERSION`
- AND `app.__version__` (re-exported from `core`) equals `core.__version__`

## ADDED Requirements

### Requirement: `--version` CLI flag prints version and exits 0

`cli.py` SHALL accept a `--version` flag on its argument parser. When invoked,
the CLI SHALL print `%(prog)s {__version__}` (where `__version__` is imported
from `core`) to stdout and exit with status 0, WITHOUT performing any fetch or
cache operation. The flag SHALL be implemented via argparse
`action="version"` (or equivalent behavior) so that no query-mode argument is
required and the normal fetch path is not reached.

#### Scenario: `--version` prints the version and exits 0

- GIVEN the CLI parser is built with `--version` wired to `core.__version__`
- WHEN `cli.run(["--version"])` (or `cli.main(["--version"])`) is invoked
- THEN the process raises `SystemExit` with code 0
- AND the captured stdout contains the value of `core.__version__` (e.g. `"1.0.0"`)

#### Scenario: `--version` does not perform a fetch

- GIVEN no network is available and no cache exists
- WHEN `cli.run(["--version"])` is invoked
- THEN no `core.fetch_*` call is made and no cache access occurs (the version
  path exits before any query mode is evaluated)

## Out of Scope

- Semver / PEP 440 compliance enforcement on the `__version__` string.
- A `--version` flag on the GUI surface (GUI exposes version via "Acerca de" only).
- Reading the version from package metadata / `importlib.metadata` (the single
  source remains the `core.__version__` literal for this change).
