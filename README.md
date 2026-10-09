# SUNAT Exchange Rate App

![License](https://img.shields.io/badge/license-PolyForm%20NC%201.0.0-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)

> Desktop GUI and CLI in Python to query the official exchange rate published by SUNAT, with local SQLite caching and Excel export.

## Overview

Python application (Tkinter) to query the **Official Exchange Rate** published by SUNAT (Peru's tax authority). It has **two modes**:

- **GUI** (default): window with a results table, quick filters, copy to clipboard and Excel export.
- **CLI** (with arguments): for terminal use, cron/Task Scheduler jobs, or pipelines.

Data is cached locally in SQLite so repeated queries are instant.

<div align="center">
<img width="852" height="632" alt="SUNAT Exchange Rate App" src="https://github.com/user-attachments/assets/c8b0c9c7-25b9-4a9e-9c96-dce52c28ba5e" />
</div>

## Features

- **Two modes**: interactive Tkinter GUI and a full argparse-based CLI sharing the same data layer.
- **Query modes**: today, yesterday, arbitrary date range, or a full month.
- **Quick filters** in the GUI: Today · Yesterday · Last 7 days · Last 30 days · This month · Last month.
- **Optional API token**: with a token, month and range queries resolve in **one request per month** (~1 s); without it, months are rebuilt day by day (minutes, due to the public API's ~20 req/min limit). Configure it in the GUI (**Configurar token…**) or with the `SUNAT_TC_TOKEN` environment variable.
- **Local SQLite cache**: past dates are served instantly; repeat queries come from the cache in <100 ms.
- **Export** results to Excel (.xlsx, shared between GUI and CLI) or CSV (UTF-8 with BOM, ready for Excel).
- **JSON output** for pipelines (`--json`).
- **Window state persistence** (`state.json`): geometry, mode and dates are restored between sessions.
- **Robust networking**: typed errors with retries and exponential backoff (3 attempts), rotating log file.
- Cache management from both modes (info, clear).

## Tech Stack

- **Python 3.9+** with `requests`, `openpyxl` and `tkinter` (bundled with Python).
- **SQLite** for the local cache (stdlib `sqlite3`).
- Tests with `pytest` (+ `pytest-mock`, `requests-mock`); linting with `ruff`.

## Requirements

- Python 3.9 or higher.
- Internet connection.
- Tkinter (included by default on Windows; on Linux: `sudo apt install python3-tk`).

## Installation

```powershell
cd D:\Proyectos\Scripts\sunat-tc-app
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Usage

### GUI mode

```powershell
# Double-click run.bat, or:
python app.py
```

1. Choose a mode: **Today** / **Date range** / **Full month**.
2. Set the dates with the DD/MM/YYYY selectors.
3. **Or** use the **quick filters**: Today · Yesterday · Last 7 days · Last 30 days · This month · Last month.
4. Press **Query** (or a quick filter, which queries automatically).
5. Copy to clipboard (Ctrl+C) or export to Excel (Ctrl+E).

**Bottom buttons:**

- Copy selection · Copy all
- **Clear cache** — deletes the local SQLite database
- **Configurar token…** — saves/removes the optional API token (see below)
- Export to Excel…

**Cache indicator** (bottom-right corner): shows how many dates are cached and the range. Click for details.

**What is saved between sessions?** On close, the app persists to `%APPDATA%\sunat-tc-app\state.json`: window position and size, selected mode (Today / Range / Month), and the range dates or month/year. Everything is restored on the next launch.

### API token (optional)

Without a token the app uses the free public API, which only answers **one day per request** and throttles to ~20 requests/minute, so a full month is rebuilt day by day (a couple of minutes the first time). With a token (same provider: [apis.net.pe](https://apis.net.pe/api-tipo-cambio.html) / decolecta) the whole month arrives in **one request** (about a second).

- **GUI**: **Configurar token…** → paste the token → **Guardar**. The app verifies it against the API and stores it in `%APPDATA%\sunat-tc-app\config.json` (never in the repository or the logs). Use **Quitar token** to remove it.
- **Environment variable** `SUNAT_TC_TOKEN` overrides the saved file (handy for scheduled CLI jobs).
- The token is optional: without it everything keeps working, just slower for months/ranges.

### CLI mode

```powershell
# Help
python app.py --help

# Today's exchange rate
python app.py --today

# Yesterday's exchange rate
python app.py --yesterday

# Date range
python app.py --range 2024-01-01:2024-12-31

# Full month
python app.py --month 2024-12

# JSON output
python app.py --today --json

# Save as CSV
python app.py --range 2024-01-01:2024-12-31 --csv tc_2024.csv

# Save as Excel
python app.py --month 2024-12 --xlsx tc_diciembre.xlsx

# Skip cache (force API)
python app.py --today --no-cache

# Cache info
python app.py --cache-info

# Clear cache
python app.py --clear-cache
```

**CLI exit codes:**

| Code | Meaning |
|---|---|
| 0 | OK (also `--help` and `--version`) |
| 1 | No arguments (no query flag) |
| 2 | Invalid arguments |
| 3 | No data found |
| 4 | API error |
| 5 | Write error (CSV/XLSX) |

## Advanced Usage

Bash pipeline to download and process:

```bash
python app.py --range 2024-01-01:2024-12-31 --json | jq '[.[] | .compra] | add/length'
```

Windows Task Scheduler to update an Excel file every morning at 9 AM:

```text
Program:    C:\Proyectos\Scripts\sunat-tc-app\run.bat
Arguments:  --range 2024-01-01:%date:~-4%%date:~3,2%%date:~0,2% --xlsx "D:\Reportes\tc.xlsx"
```

### CSV encoding

Files generated with `--csv` are written in **UTF-8 with BOM** (the first
three bytes are `EF BB BF`). This makes Microsoft Excel on Windows open the
file with the correct encoding by default, with no manual "Data > From Text"
steps. The BOM is **mandatory** in this version; there is no `--csv-bom`
flag to disable it.

`--json` output is **not affected** — it stays pure UTF-8, suitable for `jq`,
redirecting into another process's `stdin`, or parsing in any language.

## Project Structure

```text
sunat-tc-app/
├── app.py             # GUI + entry point (dispatches to GUI or CLI based on argv)
├── cli.py             # CLI mode (argparse)
├── core/              # Data layer (package)
│   ├── __init__.py    # Fetching, SQLite cache, state persistence, re-exports
│   ├── errors.py      # Typed FetchError
│   ├── locale.py      # MONTHS_ES / MONTHS_ABBR_ES
│   ├── validators.py  # validate_range / validate_month + MIN_YEAR/MAX_RANGE_DAYS
│   ├── messages.py    # format_fetch_error (Spanish FetchError message mapper)
│   └── excel.py       # write_xlsx — shared Excel export (CLI + GUI)
├── tests/             # pytest suite
├── openspec/          # SDD workspace (specs + changes)
├── requirements.txt   # requests, openpyxl
├── requirements-dev.txt  # pytest, pytest-mock, requests-mock, ruff
├── pytest.ini
├── run.bat            # Windows launcher
├── LICENSE
└── README.md
```

Code responsibilities:

| File | Responsibility |
|---|---|
| `core/__init__.py` | Data layer: HTTP with retries (v1 public + v2 with token), normalization, SQLite cache, JSON state/config. No UI. Public re-exports. |
| `core/errors.py` | Typed `FetchError` (kinds: network/http_4xx/http_5xx/parse/rate_limit/auth/input). |
| `core/locale.py` | `MONTHS_ES` / `MONTHS_ABBR_ES` for the Spanish UI. |
| `core/validators.py` | `validate_range` / `validate_month` + `MIN_YEAR` / `MAX_RANGE_DAYS` constants. |
| `core/messages.py` | `format_fetch_error` — maps `FetchError` to Spanish messages. |
| `core/excel.py` | `write_xlsx` — formatted Excel export shared by CLI and GUI (lazy openpyxl). |
| `app.py` | GUI: `DateEntry`, `SunatTCApp`, quick filters, Excel export. Dispatches to CLI when argv is present. |
| `cli.py` | argparse, stdout/JSON/CSV/XLSX output, cache sub-commands. |

`core/` is the only layer that touches the network and the disk. Both the GUI and the CLI consume it.

## Notes

- **Data source**: [apis.net.pe](https://apis.net.pe) — a public API that mirrors SUNAT's official exchange rate. No API key required; an optional token (see above) switches month/range queries to the v2 endpoint.
- On weekends and holidays SUNAT publishes no new rate; the API returns the previous business day's closing rate for those dates (per SUNAT's own note).
- The API has no data for dates before 2000.
- Network errors are retried with backoff (3 attempts); retries and network/HTTP errors are logged to `%APPDATA%\sunat-tc-app\app.log` (rotating, 512 KB × 3 files). The API token is never written to the log.
- **Cache location**: `%APPDATA%\sunat-tc-app\cache.db` (Windows) / `~/.local/share/sunat-tc-app/cache.db` (Linux/macOS). Everything is cached (buy, sell, date, source, download timestamp). Past dates always use the cache; today's rate is re-fetched every time (it can change). Clear it with the "Clear cache" button or `python app.py --clear-cache`.
- **Config location**: `%APPDATA%\sunat-tc-app\config.json` (optional API token).

## License

Distributed under the **PolyForm Noncommercial License 1.0.0** — free for
noncommercial use only. See [LICENSE](LICENSE) for the full license text.

Copyright (c) 2026 Jose Miguel Maldonado Garcia

## Author

**Jose Miguel Maldonado Garcia** — [@JoanMike](https://github.com/JoanMike)
