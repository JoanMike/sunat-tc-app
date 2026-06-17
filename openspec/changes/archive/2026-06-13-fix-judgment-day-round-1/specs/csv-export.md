# CSV Export Specification

## Purpose

Defines the encoding used by the CLI's `--csv` export so the file opens
correctly in Microsoft Excel on Windows without manual encoding
selection. References: Engram `#1879` (finding #7), cached product
decision 1A.

## Requirements

### Requirement: CSV written with UTF-8 BOM by default

`cli._save_csv` SHALL open the destination file with the `"utf-8-sig"`
codec, which writes the three-byte BOM sequence `EF BB BF` at the start
of the file. This applies to every `--csv` invocation in this change
cycle; no caller option toggles it off.

#### Scenario: First bytes are the UTF-8 BOM
- GIVEN a successful `--csv` export
- WHEN the first three bytes of the file are read
- THEN they are `EF BB BF`

#### Scenario: Excel renders accents correctly
- GIVEN a CSV file produced by the CLI
- WHEN the file is opened in Microsoft Excel on Windows
- THEN accented characters (e.g. in column headers and dates) render
  correctly without the user having to pick an encoding

### Requirement: No `--csv-bom` flag in this cycle

The CLI SHALL NOT expose a `--csv-bom` flag (or any flag that toggles
the BOM) in this change. The BOM is always on; rolling back to no-BOM
is a one-line code change captured in the proposal's Rollback Plan.
Consumers that need a BOM-free stream SHALL use `--json` instead.

#### Scenario: Help output omits the BOM flag
- GIVEN the user runs `python app.py --help`
- WHEN the parser prints the usage text
- THEN no `--csv-bom` (or equivalent) flag appears

## Out of Scope

- A `--csv-bom` toggle (explicitly deferred; see proposal §Out of Scope).
- Changes to the JSON or XLSX output paths; JSON is unaffected by the
  BOM and XLSX has its own encoding rules.
- CSV dialect configuration (delimiter, quoting, line terminator).
