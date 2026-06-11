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
├── core.py         # Pure data layer: HTTP retry, SQLite cache, JSON state. NO UI.
├── requirements.txt
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
| `core.py` | `requests`, `sqlite3`, `calendar`, `datetime`, `pathlib` | `fetch_day`, `fetch_month`, `fetch_range`, `cache_*`, `load_state`, `save_state` | Network I/O, SQLite at `%APPDATA%\sunat-tc-app\cache.db`, JSON state at `%APPDATA%\sunat-tc-app\state.json`, creates app data dir on import |
| `cli.py` | `argparse`, `csv`, `json`, `openpyxl`, `core` | `run(argv)`, `main()` | stdout/stderr, file writes (CSV/XLSX) |
| `app.py` | `tkinter`, `queue`, `threading`, `openpyxl`, `core`, `cli` | `SunatTCApp`, `DateEntry`, `main()` | Tk window, clipboard, XLSX export, background worker threads |

`core.py` is the only module that touches the network or persistent disk. GUI and CLI both
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
- **Error handling**: `_get_with_retry` collapses every failure to `[]` (Judgment Day finding
  #3) — fixes are queued for `fix/judgment-day-round-1`.

## Testing capabilities

- **Test runner**: NONE. No `pytest`, `unittest` discovery config, or alternative runner
  installed.
- **Coverage**: NONE.
- **Linter / type checker / formatter**: NONE.
- **`strict_tdd`**: `false` (in `config.yaml`).

Implication for the upcoming `fix/judgment-day-round-1` change: fixes will be applied and
verified manually + by reading code. Recommend bootstrapping `pytest` before any
behavior-changing fix that touches `core.py` HTTP/cache logic.

## Persistence

- **Artifact store**: `openspec/` (file artifacts). Engram used as secondary cache for
  state/registry/testing-caps.
- **Engram topic key for init**: `sdd-init/sunat-tc-app`
- **Engram topic key for testing capabilities**: `sdd/sunat-tc-app/testing-capabilities`
- **Engram topic key for skill registry**: `skill-registry`
- **Engram topic key for prior review (READ-ONLY context)**: `judgment-day/sunat-tc-app/round-1`

## Upcoming change: `fix/judgment-day-round-1`

Source synthesis: Engram observation #1879 (`judgment-day/sunat-tc-app/round-1`).

**15 real findings** to address in a single change cycle (option A from user):
- 7 confirmed WARNING (real) — both judges agreed
- 8 suspect WARNING (real) — one judge flagged, re-judged as real during synthesis
- 0 CRITICAL
- 5 confirmed SUGGESTION (lower priority, may be batched)

### Confirmed WARNING (7) — both judges, must fix

1. `app.py:586` — `_cancelled` dead field, never read after write.
2. `core.py:336` — `fetch_range` sleeps 0.3s/month unconditionally, even on full cache hit.
3. `core.py:107-122` — `_get_with_retry` swallows every failure as `[]`; no distinction
   between network error, 4xx, 5xx, or JSON parse error.
4. `app.py` — No cancel path for in-flight worker threads.
5. `cli.py:204-218` — `--range` lacks `end <= today` validation and 730-day cap.
6. `cli.py:219-229` — `--month` lacks MIN_YEAR/MAX_YEAR bounds.
7. `cli.py:115-120` — CSV written as UTF-8 without BOM → Excel mojibake on Windows.

### Suspect WARNING (8) — re-judged as real

- `or` falsy-zero in `_normalize_item` (Judge B)
- `geometry` TclError on first launch (Judge B)
- `core.py` import-time `mkdir` side effect (Judge B)
- Eager `openpyxl` import in `app.py` (Judge B)
- "Sin datos" status painted green (Judge A)
- `os.startfile` wrapped in bare `except: pass` (Judge A)
- Quick-filter click during worker is silent no-op (Judge B)
- English `month_abbr` in Spanish UI (Judge A)

### Confirmed SUGGESTION (5)

Lower-priority polish. May be batched into a follow-up change if scope gets too large.

### Change shape

- **Name**: `fix/judgment-day-round-1`
- **Type**: behavior fix + small refactor
- **Strict TDD**: off for now (bootstrap pytest first, or apply fixes without tests)
- **Chained PR strategy**: `ask-always` (review budget 400 lines per PR)
- **Review budget**: 400 lines
- **Recommended split**: at minimum separate `core.py` (data layer, fully testable) from
  `app.py` (GUI) and `cli.py` (CLI). Likely 2-3 chained PRs.

## What this AGENTS.md is NOT

- Not a build manifest — see `requirements.txt` and `run.bat`.
- Not the source of truth for SDD config — see `config.yaml`.
- Not a changelog — see commit history and `openspec/changes/archive/`.
