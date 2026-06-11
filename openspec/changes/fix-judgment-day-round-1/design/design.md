# Design: fix/judgment-day-round-1

## Technical Approach

A **3-chained-PR** implementation of the 15 Judgment Day findings, organized
by dependency layer (data → CLI → GUI). The `core` data layer is fixed and
fully unit-tested first (PR 1); CLI is rewired to consume the new helpers
and typed errors (PR 2); the GUI gets cancel/token/status/import-hygiene
changes last (PR 3). All user-facing strings are Spanish; all identifiers
and exception class names are English.

```
core.py ──typed errors──▶ cli.py
   │                          │
   │                          └──(no auto-cancel on quick-filter, decision 2A)
   │                              │
   └──────validators, MONTHS_ES, BOM──▶ app.py
                                          │
                                          └──Cancelar button + _worker_token
```

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|----------|--------|----------------------|-----------|
| D1 | `FetchError` shape | Single class `FetchError(Exception)` with `kind: str ∈ {"network","http_4xx","http_5xx","parse"}` and `__cause__` chain. **Lives in new `core/errors.py`.** | Class hierarchy (`NetworkError(HttpStatusError(...))`) | The spec already mandates `kind` as a discriminator; subclassing adds indirection without runtime value. One module = one place to evolve. |
| D2 | Retry schedule | `max_retries=3`, base delays `[0.5, 1.0, 2.0]`, jitter `random.uniform(0, delay)` **added to** the base sleep. Jitter modifies sleep, never the next attempt. | Constant sleep; exponential without jitter | Matches proposal intent; jitter avoids thundering herd; tested via `time.sleep` mock. |
| D3 | Cache-hit short-circuit in `fetch_range` | For each month call `cache_get_month(y, m)`; if `len(cached) >= MIN_DAYS_FOR_CACHED_MONTH` and not current month, reuse. Track `network_happened = False`; only call `time.sleep(0.3)` when `network_happened == True` for the **previous** month iteration. | Pre-check all months up-front (extra DB hit) | Incremental check matches existing `fetch_month` semantics; single source of truth for the "cached?" predicate. |
| D4 | Quick-filter during worker | **Show non-blocking Spanish message `"Espere a que termine la consulta."` in status bar; do NOT auto-cancel, do NOT auto-start a new query.** | Auto-cancel + restart (suggested in orchestrator brief) | Cached product decision **2A binds** us to explicit-cancel-only. Auto-restart would race with the running worker for `_worker_token` and confuse the user. Honoring 2A is the safest path. |
| D5 | Generation token | `self._worker_token: int = 0` on `SunatTCApp`; increment in `_on_fetch` *before* `Thread.start()`. Token is captured by the `_on_fetch_done` closure and compared to `self._worker_token` at the top of `_update`; mismatch → silent return (no table touch, no status, no count). | `threading.Event`; queue-based | Integer counter is the smallest correct primitive; no per-callback allocation; works with Tk's `after(0, ...)` scheduler. |
| D6 | Cancel mechanism | `self._cancel_event = threading.Event()` on `SunatTCApp`; `_on_cancel` calls `.set()` and sets a status text `"Cancelando…"`; `_fetch_worker` checks `cancel_event.is_set()` between each call to `fetch_day`/`fetch_month`/`fetch_range` and after each `on_progress`. | Killing the thread (impossible in Python) | Cooperative cancel is the only safe pattern. Python cannot interrupt blocking I/O. Stale results are dropped by the token. |
| D7 | `MONTHS_ES` / `MONTHS_ABBR_ES` location | **New `core/locale.py`** with 13-element lists (index 0 unused). Imported by `core` (re-export) and `app`. | Top-of-`core.py` constants | Per the spec, localization is its own concern; putting it in a 20-line module keeps `core.py` focused on data-layer logic. |
| D8 | Validator location | `core/validators.py` with `validate_range(start: date, end: date) -> tuple[date, date] \| str` and `validate_month(year: int, month: int) -> tuple[int, int] \| str`. **Re-exported from `core`** so callers do `from core import validate_range`. | Inline in `core.py`; new `cli/validators.py` | Single source of truth; `from core import` is the existing import convention. |
| D9 | Test harness | `tests/conftest.py` with `tmp_path` fixture + `monkeypatch` to override `core.CACHE_DB` and `core.STATE_FILE` per test; `requests_mock` (per orchestrator brief) to stub `requests.get`. `pytest.ini` with `testpaths = tests`, `python_files = test_*.py`. `requirements-dev.txt` with `pytest>=7`, `pytest-cov>=4`, `requests-mock>=1.10`. | `unittest`; `responses` | The user asked for `requests_mock`. `tmp_path` is stdlib; no extra fixture lib needed. |
| D10 | Lazy `openpyxl` | Both `app.py` and `cli.py` remove the top-level `from openpyxl import ...`; imports move to the first line of `_export_excel` (app) and `_save_xlsx` (cli). | Lazy module wrapper; `importlib` indirection | Direct inline import is the most readable pattern. The spec scenario "Importing `app` does not load `openpyxl`" is satisfied trivially. |
| D11 | `os.startfile` helper | New private `SunatTCApp._abrir_carpeta(path: str) -> bool`. Both call sites (cache-info, export-complete) use it. On `OSError`: `logger.warning("os.startfile failed for %s: %s", path, exc)` + `messagebox.showerror("Error al abrir carpeta", f"No se pudo abrir la carpeta:\n{path}")`. Returns `True` on success. | `print(..., file=sys.stderr)` | The spec allows either; `logging` is more configurable and matches stdlib best practice. |
| D12 | `geometry` fallback | `geo = self.state.get("geometry", "850x600"); try: self.root.geometry(geo) except tk.TclError: self.root.geometry("850x600"); self.state["geometry"] = "850x600"` — also persist the fallback so the next launch is clean. | Validate string with regex; ignore silently | Spec mandates fall back to `850x600` and re-persist. Regex is brittle. |
| D13 | `save_state` surfacing | Capture return value at `app.py:_on_close`: `if not save_state(self.state): messagebox.showwarning("Estado", "No se pudo guardar la configuración.")`. Wrap in `try/except OSError` as a safety net (the function returns `False` on known `OSError`, but we guard against any future raise). | Swallow the False | The spec says `save_state` returns `bool`; honoring the contract and surfacing failure is the user-visible win. |
| D14 | Cancellation of `core` change blast radius | `_get_with_retry` no longer returns `[]` on persistent failure. `fetch_day` / `fetch_month` / `fetch_range` **translate** `FetchError` into their own return contract: `fetch_day` raises `FetchError` (no silent swallow); `fetch_month` raises `FetchError`; `fetch_range` raises `FetchError`. Callers (CLI / GUI worker) catch `FetchError` and decide. | Catch inside `core`, return `[]` for one path and raise for another | Cleanest: data layer surfaces truth; presentation layer decides what "no data" means. Documented in each function's docstring. |
| D15 | Status bar color taxonomy | Three foreground colors: `INFO = "#1f6feb"` (busy/progress), `OK = "#2da44e"` (success), `NEUTRAL = "#555"` ("Sin datos", "Caché borrado", "No se encontraron datos…"). New constant block at top of `app.py` so the values are searchable. | Per-call hex literals | Centralized constants reduce drift and make theme changes one-edit. |

## Per-Capability Design

### `data-fetch` (PR 1)

- New `core/errors.py` with `FetchError` (D1). The class carries `kind`,
  `message`, and a `__cause__` chain.
- `_get_with_retry` rewritten: catches `requests.RequestException` → raise
  `FetchError(kind="network")` after retries exhausted; 4xx → raise
  `FetchError(kind="http_4xx", status=code)`; 5xx → raise
  `FetchError(kind="http_5xx", status=code)`; `ValueError` on JSON parse →
  raise `FetchError(kind="parse")`. 404/204 still return `[]` (legitimately
  no data, per spec).
- `_normalize_item`: replace `compra = item.get("compra") or item.get("buyPrice")`
  with `compra = item.get("compra"); if compra is None: compra = item.get("buyPrice")`.
  Same for `venta`. Preserves `0` (D14).
- `fetch_range`: track `network_happened` per iteration. Skip the trailing
  `time.sleep(0.3)` when the current month was served entirely from cache
  (D3).
- New private `_ensure_app_data_dir()` called from `_connect()`. `mkdir`
  removed from `_app_data_dir()` and `CACHE_DB` / `STATE_FILE` are no longer
  computed at import time; they are computed lazily on first cache/state use.

### `input-validation` (PR 1 + PR 2 + PR 3)

- New `core/validators.py` with `validate_range` and `validate_month`
  returning `tuple | str` (D8).
- `app.SunatTCApp._validate_inputs` becomes a thin wrapper: call the shared
  helper, translate the `str` into a `messagebox.showwarning` (PR 3).
- `cli.run` calls the same helpers; `str` becomes a Spanish `print(..., file=sys.stderr)`
  + `return 2` (PR 2).
- Spanish error messages are **constant strings** at the top of `validators.py`
  (single source of truth).

### `csv-export` (PR 2)

- `cli._save_csv`: change `encoding="utf-8"` → `encoding="utf-8-sig"`. No
  signature change; no new flag.

### `localization` (PR 1 + PR 3)

- New `core/locale.py` with `MONTHS_ES` (full) and `MONTHS_ABBR_ES` (abbrev).
- `core.fetch_range` uses `MONTHS_ABBR_ES[m]` in the progress string
  (replacing `calendar.month_abbr[m]`).
- `app.SunatTCApp._fetch_worker` uses `MONTHS_ES[params['month']]`
  (replacing `calendar.month_name[params['month']]`).
- All new user-visible strings (error messages, cancel labels, status
  text) authored in Spanish; class names stay English.

### `gui-worker-lifecycle` (PR 3)

- Remove `self._cancelled` (S1).
- Add `self._worker_token: int = 0` and `self._cancel_event = threading.Event()`
  in `__init__`.
- Add `Cancelar` button next to `Consultar`; visible only while worker alive.
  Click handler: `self._cancel_event.set(); self._set_busy(True, "Cancelando…")`.
- In `_on_fetch`: if a worker is alive, show `"Espere a que termine la consulta."`
  in the status bar and return early (D4).
- Increment `self._worker_token` and **clear** the event before starting a
  new thread.
- `_fetch_worker` checks `self._cancel_event.is_set()` between each major
  step and after each progress update; if set, calls `on_done([], "Consulta cancelada.")`
  and returns.
- `_on_fetch_done`'s `_update` closure captures the token; if
  `captured != self._worker_token`, return immediately (no table, no status,
  no count). D5.
- New color constants block at top of `app.py` (D15). `_set_busy(False, "No se encontraron datos…")`
  uses `NEUTRAL`; `_set_busy(False, f"Se obtuvieron {N} registro(s).")` uses `OK`.
  Worker-start path uses `INFO`.

### `app-startup-and-imports` (PR 3)

- Remove `from openpyxl import ...` at top of `app.py`; move into
  `_export_excel` (D10).
- Wrap `self.root.geometry(self.state.get("geometry", "850x600"))` in
  `try/except tk.TclError` with `850x600` fallback and re-persist (D12).
- New `SunatTCApp._abrir_carpeta(path) -> bool` (D11). Both `os.startfile`
  call sites use it. On `OSError` → `logger.warning(...)` +
  `messagebox.showerror(...)`.
- `cli._save_xlsx` lazy-imports `openpyxl` (D10). `cli.py` top-of-file
  `from openpyxl import ...` removed.
- `core.save_state` return captured at `app._on_close` (D13).

## File Changes

| File | Action | LoC budget | Notes |
|------|--------|------------|-------|
| `core.py` | Modify | +60 / -20 | D1, D3, D7 re-export, D8 re-export, D14 rewrite of `_get_with_retry`, D10 mkdir, `_normalize_item` falsy-zero fix |
| `core/__init__.py` | Create | 5 | Re-export public surface so `from core import ...` keeps working (optional; if flat module, skip) |
| `core/errors.py` | Create | 25 | `FetchError` class |
| `core/locale.py` | Create | 25 | `MONTHS_ES` + `MONTHS_ABBR_ES` |
| `core/validators.py` | Create | 55 | `validate_range`, `validate_month`, MIN/MAX constants |
| `cli.py` | Modify | +40 / -25 | Validator wiring, BOM default, lazy openpyxl, error mapping |
| `app.py` | Modify | +180 / -50 | Theme D (cancel, token, status colors, quick-filter), Theme E (lazy import, geometry, os.startfile helper) |
| `tests/conftest.py` | Create | 45 | `tmp_path` + `monkeypatch` of `CACHE_DB`/`STATE_FILE`; `requests_mock` autouse |
| `tests/test_core.py` | Create | 160 | normalize, coerce, retry (4 kinds), cache CRUD, fetch_range cache-hit short-circuit |
| `tests/test_validators.py` | Create | 80 | `validate_range` (3 paths), `validate_month` (2 paths) |
| `tests/test_cli.py` | Create | 90 | `--range`/`--month` exit code 2 paths; CSV BOM bytes; `--help` omits BOM flag |
| `pytest.ini` | Create | 5 | `testpaths = tests`, `python_files = test_*.py` |
| `requirements-dev.txt` | Create | 5 | pytest, pytest-cov, requests-mock |
| `openspec/config.yaml` | Modify | +5 / -3 | Flip `strict_tdd: true`; populate `apply.test_command` and `verify.test_command` |
| `README.md` | Modify | +8 / -2 | Document BOM, JSON path unaffected |

**Total: 5 new files, 5 modified files, ~720 added / ~100 deleted net ≈ 620 LoC.**

## Interfaces / Contracts

```python
# core/errors.py
class FetchError(Exception):
    kinds = ("network", "http_4xx", "http_5xx", "parse")
    def __init__(self, kind: str, message: str = "", *, status: int | None = None) -> None:
        super().__init__(message or kind)
        self.kind = kind
        self.status = status  # for http_*xx kinds

# core/locale.py
MONTHS_ABBR_ES: list[str] = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
                              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MONTHS_ES: list[str] = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# core/validators.py
MIN_RANGE_DAYS: int = 1
MAX_RANGE_DAYS: int = 730
def validate_range(start: date, end: date) -> tuple[date, date] | str: ...
def validate_month(year: int, month: int) -> tuple[int, int] | str: ...
```

```python
# app.py (additions)
class SunatTCApp:
    _COLOR_INFO = "#1f6feb"
    _COLOR_OK = "#2da44e"
    _COLOR_NEUTRAL = "#555"
    def __init__(self, ...):
        self._worker_token: int = 0
        self._cancel_event: threading.Event = threading.Event()
        ...
    def _on_cancel(self) -> None: ...
    def _abrir_carpeta(self, path: str) -> bool: ...
```

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit (PR 1) | `_normalize_item` falsy-zero, `_coerce_list` edges, `_get_with_retry` 4 `FetchError` kinds + 404 not-an-error, `cache_*` CRUD against `tmp_path` DB, `fetch_range` cache-hit short-circuit, `validate_range` 3 paths, `validate_month` 2 paths, `MONTHS_ES` indices | `pytest` + `requests_mock`; `monkeypatch.setattr(core, "CACHE_DB", tmp_path/"c.db")` per test |
| Unit (PR 2) | CLI `--range`/`--month` exit 2 with Spanish stderr; `--csv` first 3 bytes == BOM; `--help` has no `--csv-bom` flag | `capsys` + `argparse` parsing of `cli.run([...])` |
| Unit (PR 3) | `validate_range` round-trips through GUI `_validate_inputs`; `_abrir_carpeta` returns False on `OSError`; `geometry` fallback path | `monkeypatch.setattr("tk.Tk.geometry", lambda *a, **k: (_ for _ in ()).throw(tk.TclError))` |
| E2E / smoke | GUI start → fetch today → cancel → fetch month → export XLSX → export CSV | Manual; recorded in PR description (no CI driver) |

Strict TDD is active from PR 1's first behavior-changing task (decision 3A).
Task 0 (bootstrap) is **not** test-first.

## Chained PR Plan

| PR | Scope | LoC diff (add+del) | Review time | Base | Acceptance |
|----|-------|--------------------|-------------|------|-----------|
| **PR 1** | bootstrap pytest + Theme A (errors/cache/falsy-zero/mkdir) + Theme B helpers + Theme C locale & BOM constant in `core` only | **~350** | 45 min | `main` | S2, S3, S8, S10, S15 (locale); pytest green ≥20 tests |
| **PR 2** | Wire `validate_range`/`validate_month` into `cli.run`; switch `_save_csv` to `utf-8-sig`; lazy openpyxl; typed-error mapping | **~150** | 25 min | `main` (after PR 1 merges) | S5, S6, S7; CSV bytes `EF BB BF` |
| **PR 3** | Theme D (cancel, token, status colors, quick-filter message) + Theme E (lazy import, geometry, os.startfile helper); remove `_cancelled` | **~300** | 45 min | `main` (after PR 2 merges) | S1, S4, S9, S11, S12, S13, S14; manual smoke |

**4-PR fallback** (triggered only if PR 1 > 400 LoC after tests):
- **PR 1a** — bootstrap pytest + Theme A only (`core/errors.py` + `_get_with_retry` rewrite + cache-hit short-circuit + `_normalize_item` fix + lazy mkdir). **~220 LoC.**
- **PR 1b** — `core/validators.py` + `core/locale.py` + `cli._save_csv` BOM + `validate_*` callers in `core.fetch_*` progress strings. **~180 LoC.**
- PR 2 and PR 3 unchanged.

**Strategy**: **stacked-to-main** (each PR merges to `main` in order; child
PRs target `main` after the previous merges). Chosen because the slices are
genuinely independent and reviewers benefit from a clean history per layer.

## Commit Plan per PR

Per `work-unit-commits`: each commit = one concern, tests in the same commit.

**PR 1** (target: ~6 commits):
1. `chore(deps): add pytest + requests-mock to requirements-dev.txt`
2. `chore(ci): bootstrap pytest harness (pytest.ini, tests/conftest.py, smoke test)`
3. `feat(core): introduce FetchError and typed error contract`
4. `feat(core): preserve numeric 0 in _normalize_item, lazy mkdir in _connect`
5. `feat(core): cache-hit short-circuit in fetch_range`
6. `feat(core): MONTHS_ES locale and validate_range/validate_month helpers`
7. `docs: flip strict_tdd: true in openspec/config.yaml`

**PR 2** (target: ~3 commits):
1. `refactor(cli): wire core.validate_range and core.validate_month`
2. `feat(cli): map FetchError to Spanish stderr messages`
3. `feat(cli): csv with utf-8-sig BOM; lazy openpyxl in _save_xlsx`

**PR 3** (target: ~6 commits):
1. `refactor(app): remove dead _cancelled field`
2. `feat(app): introduce _worker_token and cancel Event`
3. `feat(app): Cancelar button wired to cancel event + status text`
4. `feat(app): status bar color taxonomy (info/ok/neutral)`
5. `feat(app): geometry TclError fallback with 850x600`
6. `feat(app): lazy openpyxl in _export_excel; _abrir_carpeta helper`
7. `docs: README documents CSV BOM and JSON exemption`

Each commit leaves the repo in a runnable state (no half-implemented
features merged); `pytest -q` is green after every commit.

## Migration / Rollback

- **No data migration.** Cache (`%APPDATA%\sunat-tc-app\cache.db`) schema
  unchanged. State (`state.json`) is forward-compatible (a corrupt
  `geometry` triggers the new fallback; default `850x600` is a new value
  that the old app would also accept).
- **No API contract change.** External `apis.net.pe` is untouched.
- **No new runtime dep.** `openpyxl` and `requests` are already declared.
- **Per-PR revert** via `git revert`:
  - PR 1 revert → restores swallowing `_get_with_retry`, eager `mkdir`,
    falsy-zero bug, unconditional `time.sleep`; CLI/GUI still run (CLI's
    bare `except Exception` re-engages as a safety net).
  - PR 2 revert → restores ad-hoc CLI validation and BOM-less CSV.
  - PR 3 revert → restores dead `_cancelled`, no cancel button, eager
    `openpyxl`, no `geometry` fallback, swallowed `os.startfile`.
- **Test harness** (`tests/`, `pytest.ini`, `requirements-dev.txt`)
  removable without touching source. The unit tests in PR 1 do not
  modify any production code path that depends on them.

## Open Architectural Questions

- **None blocking.** All product decisions are cached (BOM always on;
  explicit cancel only; strict TDD from Task 1; Spanish UI).
- **One minor follow-up** (out of scope for this change cycle, captured for
  the next proposal): the 5 confirmed SUGGESTIONs from Judgment Day Round 1
  remain unaddressed (polish, non-blocking). The proposal explicitly defers
  them; no new spec is needed for this change.
- **One small risk to confirm during apply**: `app.py:_fetch_worker` reads
  `self.calendar.month_name` via `calendar.month_name[params['month']]`
  (line 628). The fix must import `MONTHS_ES` from `core.locale` and use
  `MONTHS_ES[params['month']]`. The D7 location choice makes that import
  obvious.
