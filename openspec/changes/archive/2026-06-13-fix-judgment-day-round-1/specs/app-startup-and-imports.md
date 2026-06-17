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

## Out of Scope

- Replacing Tkinter with another GUI toolkit.
- Cross-platform folder-open behavior beyond the existing
  `xdg-open` fallback.
- A structured logging framework; the WARNING line is a single
  `print(..., file=sys.stderr)`.
- New strings outside the scope of the 15 fixes.
