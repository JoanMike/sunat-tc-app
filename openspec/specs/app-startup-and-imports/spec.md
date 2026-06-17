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

## Out of Scope

- Replacing Tkinter with another GUI toolkit.
- Cross-platform folder-open behavior beyond the existing
  `xdg-open` fallback.
- A structured logging framework; the WARNING line is a single
  `print(..., file=sys.stderr)`.
- New strings outside the scope of the 15 fixes.
