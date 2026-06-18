# Design: docs-sync-reality

## Technical Approach

Five documentation edits across three files, ~90 LoC total. No production code, no
tests, no spec sync. The strategy is mechanical: replace each drifted passage with
current facts verified against the codebase.

## Files

| File | Items | Action |
|------|-------|--------|
| `README.md` | D1, D4 | Modify structure tree, code table, exit-codes table |
| `openspec/AGENTS.md` | D2, D5 | Modify testing section, remove upcoming-change section, fix conventions, fix module table, fix file-layout tree |
| `openspec/config.yaml` | D3 | Modify testing section + strict_tdd_reason |

## Architecture Decisions

### Decision: D1 — structure tree shows `core/` package + submodules

**Choice**: Expand the tree to list `core/` as a package with `__init__.py`, `errors.py`,
`locale.py`, `validators.py`, `messages.py`; add `tests/`, `openspec/`,
`requirements-dev.txt`, `pytest.ini`.
**Rationale**: The tree should match reality; omitting submodules and test
infrastructure misleads new contributors.

**Before** (README.md:22-30):
```
sunat-tc-app/
├── app.py             # GUI + entry point (despacha a GUI o CLI según argv)
├── cli.py             # Modo línea de comandos (argparse)
├── core.py            # Fetching, cache SQLite, persistencia de estado
├── requirements.txt   # requests, openpyxl
├── run.bat            # Lanzador para Windows
└── README.md
```

**After**:
```
sunat-tc-app/
├── app.py             # GUI + entry point (despacha a GUI o CLI según argv)
├── cli.py             # Modo línea de comandos (argparse)
├── core/              # Capa de datos (paquete)
│   ├── __init__.py    # Re-exports públicos (fetch_*, cache_*, state, errors)
│   ├── errors.py      # FetchError + kind constants
│   ├── locale.py      # MONTHS_ES, month_abbr_es
│   ├── validators.py  # validate_range, validate_month
│   └── messages.py    # format_fetch_error (Spanish user-facing messages)
├── tests/             # Pytest suite (63 tests)
├── openspec/          # SDD workspace (specs + changes)
├── requirements.txt   # requests, openpyxl
├── requirements-dev.txt  # pytest, pytest-mock, requests-mock
├── pytest.ini         # Pytest config
├── run.bat            # Lanzador para Windows
└── README.md
```

The code table (README.md:167-173) also changes `core.py` -> `core/` and the trailing
prose line (`core.py` es la unica... -> `core/` es la unica...).

### Decision: D2 — rewrite AGENTS.md testing + remove archived section + fix conventions + fix layout

**Choice**: Four edits in AGENTS.md:
1. Testing capabilities (63-73) -> reflect pytest + 63 tests + strict_tdd:true.
2. Remove "Upcoming change: fix/judgment-day-round-1" (84-128) entirely; replace with
   a one-line pointer to the archive.
3. Conventions `_get_with_retry` (60-61) -> now raises typed `FetchError`.
4. File-layout tree (17-36) -> `core.py` -> `core/` package.

**Before** (Conventions, 60-61):
```
- **Error handling**: `_get_with_retry` collapses every failure to `[]` (Judgment Day finding
  #3) — fixes are queued for `fix/judgment-day-round-1`.
```
**After**:
```
- **Error handling**: `_get_with_retry` raises typed `FetchError` (network, HTTP 4xx/5xx,
  parse) — fixed in Change A (`fix-data-layer-bugs`). See `core/errors.py`.
```

**Before** (Testing capabilities, 63-73):
```
- **Test runner**: NONE. ...
- **Coverage**: NONE.
- **Linter / type checker / formatter**: NONE.
- **`strict_tdd`**: `false` (in `config.yaml`).
```
**After**:
```
- **Test runner**: pytest (`pytest -q`). 63 tests passing across core/, cli, app.
- **Coverage**: not measured (no coverage tool installed).
- **Linter / type checker / formatter**: NONE.
- **`strict_tdd`**: `true` (in `config.yaml`).
```

### Decision: D3 — config.yaml testing section + strict_tdd_reason

**Choice**: `testing.runner: pytest`, `testing.layers.unit: true`, update
`strict_tdd_reason` to reference current state instead of the archived change cycle.
Coverage stays false (no tool installed); linter/type-checker/formatter stay false
(Change G).

**Before** (config.yaml:10-13):
```yaml
strict_tdd_reason: |
  Pytest harness is now bootstrapped (pytest.ini, tests/conftest.py, requirements-dev.txt).
  Behavior-changing tasks follow red-green-refactor from T1.3 onward in the
  `fix/judgment-day-round-1` change cycle (Engram #1881, decision 3A).
```
**After**:
```yaml
strict_tdd_reason: |
  Pytest harness bootstrapped (pytest.ini, tests/conftest.py, requirements-dev.txt).
  63 tests passing across core/, cli, and app layers. Behavior-changing tasks follow
  red-green-refactor; documentation-only changes need no RED/GREEN cycle.
```

### Decision: D4 — split exit-code row

**Before** (README.md:115-122):
```
| 0 | OK |
| 1 | Sin argumentos / help |
```
**After**:
```
| 0 | OK |
| 0 | --help (ayuda) |
| 1 | Sin argumentos (no query flag) |
```
**Rationale**: `cli.py:218-220` returns 1 for no-args; `--help` is argparse default
(exit 0). Verified: `cli.py` has no explicit `--help` handler.

### Decision: D5 — module table openpyxl -> lazy

**Before** (AGENTS.md:43-44):
```
| `cli.py` | `argparse`, `csv`, `json`, `openpyxl`, `core` | ...
| `app.py` | `tkinter`, `queue`, `threading`, `openpyxl`, `core`, `cli` | ...
```
**After**:
```
| `cli.py` | `argparse`, `csv`, `json`, `core` (openpyxl lazy in `_save_xlsx`) | ...
| `app.py` | `tkinter`, `queue`, `threading`, `core`, `cli` (openpyxl lazy in `_export_excel`) | ...
```
**Rationale**: `app.py:36-38` + `cli.py:28-30` confirm lazy imports; guarded by
`test_import_app_does_not_load_openpyxl` (`tests/test_app.py:79`).

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| None | No behavior change | `pytest -q` sanity (63/63 must hold — proves no code touched) |

## Migration / Rollout

No migration required. Rollback = `git revert`.

## Open Questions

None.
