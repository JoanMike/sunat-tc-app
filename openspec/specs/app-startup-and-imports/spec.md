# App Startup and Imports Specification

## Purpose

Defines three Windows-quirk and import-hygiene behaviors at the edges
of `app.py` and `cli.py`: lazy loading of `openpyxl`, robust
window-geometry restore, and observable failure handling for
`os.startfile`. References: Engram `#1879` (findings #9, #11, #13),
Engram `#1882` (Theme E).

## Requirements

### Requirement: Lazy `openpyxl` import in GUI and CLI

`app.py` SHALL NOT import `openpyxl` (or any of its sub-modules) at
module top-level. The import SHALL live inside `_export_excel`. The
same rule applies to `cli.py`: `_save_xlsx` SHALL import `openpyxl`
locally.

#### Scenario: Importing `app` does not load `openpyxl`
- GIVEN no export has been triggered
- WHEN `import app` is executed
- THEN `openpyxl` is not present in `sys.modules` and `app.__dict__`
  does not contain the symbol `Workbook`

#### Scenario: Export triggers the import
- GIVEN a user triggers an XLSX export from the GUI
- WHEN `_export_excel` runs
- THEN `openpyxl` is imported at that point and the file is produced

### Requirement: `geometry` TclError fallback to default size

`SunatTCApp.__init__` SHALL wrap the call
`self.root.geometry(self.state.get("geometry", "850x600"))` in a
`try/except tk.TclError`. On exception, the window SHALL be sized to
`"850x600"`. No traceback SHALL escape to the user.

#### Scenario: Corrupt geometry value
- GIVEN `state.json` contains a geometry string Tk cannot parse
- WHEN the app starts
- THEN the window opens at `850x600` and no traceback is printed

### Requirement: `os.startfile` failures are observable

Both call sites of `os.startfile` in `app.py` (the cache-info "open
folder" prompt and the export-completion "open folder" prompt) SHALL
handle `OSError` (and any subclass) by writing a WARNING-level line
to `sys.stderr` AND calling `messagebox.showerror` with a Spanish
message. The bare `except Exception: pass` pattern SHALL NOT be used.

#### Scenario: Cache folder open fails
- GIVEN the user clicks the cache label and confirms "open folder"
- WHEN `os.startfile` raises `OSError` (e.g. file association
  missing, permissions)
- THEN a Spanish `messagebox.showerror` is displayed AND a WARNING
  line is written to `sys.stderr`; the app remains responsive

#### Scenario: Export folder open fails
- GIVEN the user confirms "open folder" after an XLSX export
- WHEN `os.startfile` raises `OSError`
- THEN the same logging + dialog behavior occurs

### Requirement: Narrow exception handling in queue-drain paths

The `_poll_progress` and `_on_fetch_done` queue-drain loops in `app.py`
MUST catch only `queue.Empty` from `progress_queue.get_nowait()`. Any
other exception raised inside the loop body MUST be allowed to propagate
so it can be observed and diagnosed rather than silently swallowed.

**Rationale.** `queue.Queue.get_nowait()` is contractually only allowed
to raise `queue.Empty`; a broader catch is a stdlib best-practice
violation that hides real bugs (a typo in a future refactor could
silently raise `AttributeError` and never be seen). The two queue-drain
sites are literal instances of the bare `except Exception: pass`
pattern already prohibited by the main spec's "`os.startfile` failures
are observable" requirement. This delta brings the code into compliance
with that existing rule and gives a stable home for the contract so it
does not drift again. The other two `except Exception:` sites in
`app.py` (`_fetch_worker` at `:747` and `_export_excel` at `:946`, both
`# noqa: BLE001`) are intentionally broad user-facing error routers and
remain out of scope.

#### Scenario: Empty queue exits the drain loop cleanly

- GIVEN a `_poll_progress` or `_on_fetch_done` drain loop over
  `progress_queue`
- WHEN `progress_queue.get_nowait()` raises `queue.Empty` (queue is empty)
- THEN the drain loop exits cleanly with no uncaught exception escaping

#### Scenario: Non-Empty exception in drain loop propagates

- GIVEN a `progress_queue.get_nowait()` call inside a `_poll_progress`
  or `_on_fetch_done` drain loop
- WHEN the call raises an exception other than `queue.Empty`
  (e.g. `RuntimeError`)
- THEN the exception propagates out of the loop (it is NOT silently
  swallowed)

### Requirement: `DEFAULT_STATE` geometry matches the `minsize` floor

`core.DEFAULT_STATE["geometry"]` SHALL equal the width/height passed to
`self.root.minsize(...)` in `SunatTCApp.__init__` (`850x600`). On first launch
with no `state.json`, `load_state()` returns `dict(DEFAULT_STATE)`, so the
persisted geometry MUST already be self-consistent with the runtime `minsize`
floor and the TclError fallback default — `state.json` SHALL NOT record a
stale smaller geometry that Tk immediately clamps on render.

#### Scenario: First launch with no state.json
- GIVEN no `state.json` exists in the app data directory
- WHEN `core.load_state()` is called and the GUI initializes
- THEN the window opens at `850x600` (clamped to `minsize`)
- AND the persisted `state.json` `geometry` value is `"850x600"`

### Requirement: `today_label` refreshes on entering "Hoy" mode

`SunatTCApp._on_mode_change` SHALL recompute the "Hoy" hint label text with
`date.today()` every time the user selects "Hoy" mode. The label text MUST
reflect the current day, not the day the app was launched. This handles the
common case where the app stays open past midnight and the user re-selects
"Hoy"; continuous-across-midnight refresh without interaction is out of
scope.

#### Scenario: Stale label refreshes when re-selecting Hoy

- GIVEN the app has been open since yesterday and `today_label` still shows
  yesterday's date
- WHEN the user selects a different mode and then re-selects "Hoy"
- THEN `today_label` text contains today's date formatted `DD/MM/YYYY`

#### Scenario: Mode change away from Hoy does not error

- GIVEN "Hoy" mode is active and `today_label` is packed
- WHEN the user selects "Rango" mode
- THEN the label is unpacked and no exception is raised

### Requirement: `Ctrl+A` selects all tree rows

`SunatTCApp` SHALL bind `<Control-a>` and `<Control-A>` on `self.tree` to a
handler that selects every row. The handler MUST call
`self.tree.selection_set(self.tree.get_children())` so the existing
`selectmode="extended"` multi-select semantics apply. The binding SHALL be
scoped to `self.tree` (not `bind_all`) so it does not interfere with entry
focus.

#### Scenario: Ctrl+A selects every row

- GIVEN the table is populated with 3 rows and none are selected
- WHEN `_select_all()` is invoked (simulating `Ctrl+A`)
- THEN `len(self.tree.selection()) == 3`

#### Scenario: Ctrl+A on an empty table is a no-op

- GIVEN the table has no rows
- WHEN `_select_all()` is invoked
- THEN `len(self.tree.selection()) == 0` and no exception is raised

### Requirement: Column sort on heading click with view-following export

`SunatTCApp` SHALL make each Treeview heading (`fecha`, `compra`, `venta`)
clickable. A click SHALL sort `self.data` in place by the column's raw value
(`fecha` ISO string sorts chronologically; `compra`/`venta` are floats) and
repopulate the table from the sorted `self.data`, preserving the
`tree.index(iid) → self.data[i]` positional invariant. A second click on the
same column SHALL toggle direction; a click on a different column SHALL
switch to it ascending. The active column heading SHALL display a `▲` or
`▼` indicator. A new fetch SHALL reset sort state (`_sort_col = None`,
`_sort_desc = False`) and clear all indicators, because rows arrive
fecha-ascending from `core.fetch_range`.

Export ("Exportar") and "Copiar todo" SHALL follow the sorted order so the
export mirrors the on-screen view.

#### Scenario: Sort by compra ascending reorders data and tree

- GIVEN `self.data` holds three rows whose `compra` values are out of order
- WHEN `_sort_by_column("compra", False)` is invoked
- THEN `self.data` is sorted by `compra` ascending
- AND the tree display order matches `self.data`
- AND the `tree.index(iid) → self.data[i]` invariant still holds

#### Scenario: Re-clicking the active column toggles direction

- GIVEN `self._sort_col == "compra"` and `self._sort_desc == False`
- WHEN the "compra" heading is clicked again
- THEN `self._sort_desc` becomes `True` and the heading shows `▼`

#### Scenario: New fetch resets sort state

- GIVEN `self._sort_col == "venta"` and `self._sort_desc == True` with a `▼`
  indicator visible
- WHEN a new fetch completes and `_on_fetch_done._update` runs
- THEN `self._sort_col is None` and `self._sort_desc is False` and no heading
  shows an arrow

#### Scenario: Export follows the sorted order

- GIVEN the table is sorted descending by `venta`
- WHEN the user triggers "Exportar" or "Copiar todo"
- THEN the emitted rows follow the descending-`venta` order shown on screen

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

- Replacing Tkinter with another GUI toolkit.
- Cross-platform folder-open behavior beyond the existing
  `xdg-open` fallback.
- A structured logging framework; the WARNING line is a single
  `print(..., file=sys.stderr)`.
- New strings outside the scope of the 15 fixes.
