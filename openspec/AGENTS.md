# openspec/AGENTS.md

Agent context for the `sunat-tc-app` SDD workspace. Read this before launching any phase
(`sdd-new`, `sdd-explore`, `sdd-propose`, `sdd-spec`, `sdd-design`, `sdd-tasks`, `sdd-apply`,
`sdd-verify`, `sdd-archive`) against this project.

The authoritative schema is `openspec/config.yaml` — keep this file in sync when config changes.

## Project at a glance

- **Name**: `sunat-tc-app`
- **Purpose**: Fetches the Peru SUNAT official exchange rate (tipo de cambio) from
  `apis.net.pe` and exports to XLSX/CSV. Single-purpose utility with both GUI and CLI surfaces.
- **Runtime**: Python 3.9+. On Windows, Tkinter is bundled; on Linux install `python3-tk`.
- **Entry point**: `app.py`. With no argv → GUI; with argv → delegates to `cli.run()`.

## File layout

```
sunat-tc-app/
├── app.py          # Tkinter GUI (SunatTCApp, DateEntry), entry point
├── cli.py          # argparse CLI: --today, --yesterday, --range, --month, --json, --csv, --xlsx
├── core/           # Pure data layer (package): HTTP retry, SQLite cache, JSON state. NO UI.
│   ├── __init__.py     # Fetching, cache, state, re-exports (fetch_*, cache_*, FetchError, ...)
│   ├── errors.py       # FetchError + kind constants
│   ├── locale.py       # MONTHS_ES, MONTHS_ABBR_ES
│   ├── validators.py   # validate_range, validate_month, MIN_YEAR, MAX_RANGE_DAYS
│   └── messages.py     # format_fetch_error (Spanish FetchError mapper)
├── tests/          # Pytest suite (63 tests)
├── requirements.txt
├── requirements-dev.txt  # pytest, pytest-mock, requests-mock
├── pytest.ini      # Pytest config
├── run.bat         # Windows launcher: creates venv, installs deps, dispatches app.py
├── README.md
├── .gitignore      # Ignores venv, .atl/, runtime XLSX exports
├── venv/           # Local virtualenv (gitignored)
├── .atl/           # Local agent caches: skill-registry.md, registry cache json
└── openspec/       # SDD workspace (this directory)
    ├── config.yaml
    ├── AGENTS.md
    ├── specs/
    └── changes/
        └── archive/
```

## Module responsibilities

| Module | Imports | Exports | Side effects |
| --- | --- | --- | --- |
| `core/` | `requests`, `sqlite3`, `calendar`, `datetime`, `pathlib` | `fetch_day`, `fetch_month`, `fetch_range`, `cache_*`, `load_state`, `save_state`, `FetchError`, `format_fetch_error`, `validate_range`, `validate_month`, `MONTHS_ES` | Network I/O, SQLite at `%APPDATA%\sunat-tc-app\cache.db`, JSON state at `%APPDATA%\sunat-tc-app\state.json`, creates app data dir on import |
| `core/errors.py` | `—` | `FetchError` (kind ∈ network/http_4xx/http_5xx/parse/rate_limit/input) | None |
| `core/locale.py` | `—` | `MONTHS_ES`, `MONTHS_ABBR_ES` | None |
| `core/validators.py` | `datetime` | `validate_range`, `validate_month`, `MIN_YEAR`, `MAX_RANGE_DAYS` | None |
| `core/messages.py` | `core.errors` | `format_fetch_error` | None |
| `cli.py` | `argparse`, `csv`, `json`, `core` (openpyxl lazy in `_save_xlsx`) | `run(argv)`, `main()` | stdout/stderr, file writes (CSV/XLSX) |
| `app.py` | `tkinter`, `queue`, `threading`, `core`, `cli` (openpyxl lazy in `_export_excel`) | `SunatTCApp`, `DateEntry`, `main()` | Tk window, clipboard, XLSX export, background worker threads |

`core/` is the only package that touches the network or persistent disk. GUI and CLI both
consume it.

## Conventions

- **Language**: Source code, identifiers, comments default to **English**. UI strings
  visible to end users are **Spanish** (existing convention — see `app.py` buttons/labels).
  Do not translate the existing Spanish UI to English unless explicitly asked.
- **Style**: `from __future__ import annotations` at the top of each module. Type hints
  throughout. `snake_case` for functions/vars, `PascalCase` for classes.
- **Type hints**: Use modern union syntax (`str | None`) — already enabled via `__future__`.
- **Docstrings**: Light or absent. Match existing style unless a function is public API.
- **Paths**: Use `pathlib.Path`, not `os.path`.
- **Dates**: ISO format (`YYYY-MM-DD`) for storage and CLI; `DD/MM/YYYY` for GUI display.
- **Error handling**: `_get_with_retry` raises a typed `FetchError` (kind ∈ network/http_4xx/http_5xx/parse/rate_limit/input) on persistent failures; 404/204 return `[]` (legitimately no data). See `openspec/specs/data-fetch/spec.md`.

## Testing capabilities

- **Test runner**: pytest (`pytest -q`, 63 tests passing).
- **Coverage**: not measured.
- **Linter / type checker / formatter**: NONE (planned for a future change).
- **`strict_tdd`**: `true` (in `config.yaml`).

## Persistence

- **Artifact store**: `openspec/` (file artifacts). Engram used as secondary cache for
  state/registry/testing-caps.
- **Engram topic key for init**: `sdd-init/sunat-tc-app`
- **Engram topic key for testing capabilities**: `sdd/sunat-tc-app/testing-capabilities`
- **Engram topic key for skill registry**: `skill-registry`
- **Engram topic key for prior review (READ-ONLY context)**: `judgment-day/sunat-tc-app/round-1`

## Past changes

Past changes: see `openspec/changes/archive/` (`fix-judgment-day-round-1`, `tighten-queue-empty-mini-fix`, `fix-data-layer-bugs`, `fix-gui-lifecycle-bugs`).

## What this AGENTS.md is NOT

- Not a build manifest — see `requirements.txt` and `run.bat`.
- Not the source of truth for SDD config — see `config.yaml`.
- Not a changelog — see commit history and `openspec/changes/archive/`.
