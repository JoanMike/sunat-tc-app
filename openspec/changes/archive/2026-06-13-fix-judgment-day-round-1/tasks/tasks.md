# Tasks: fix/judgment-day-round-1

> Chained-PR implementation of 15 Judgment Day findings (Engram `#1879`) plus
> pytest bootstrap. Strategy: `stacked-to-main`. 3 PRs, 20 tasks, 16 commits.
> Strict TDD active from T1.3; T1.1/T1.2 are chore (no test-first).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~620 net LoC (≈720 added / ≈100 deleted) |
| 400-line budget risk | Low (max single PR ≈ 350 LoC) |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (core+tests) → PR 2 (cli) → PR 3 (app) |
| Delivery strategy | ask-always |
| Chain strategy | stacked-to-main |
| 4-PR fallback ready | Yes (PR 1a bootstrap+Theme A; PR 1b Theme B+C) |
| Decision needed before apply | No (under budget, user-approved) |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
```

### Per-PR Budget

| PR | Scope | LoC | % of 400 | Commits | Risk | Review min |
|----|-------|-----|----------|---------|------|------------|
| PR 1 | bootstrap + Theme A + Theme B helpers + Theme C locale | ~350 | 87% | 7 | Low | 45 |
| PR 2 | cli: validators + BOM + lazy openpyxl + typed errors | ~150 | 37% | 3 | Low | 25 |
| PR 3 | app: cancel + token + status + startup hygiene | ~300 | 75% | 6 | Low | 45 |
| **Total** | | **~620** | | **16** | **Low** | **115** |

### Work-Unit Commit Discipline

Every commit must leave the repo runnable AND `pytest -q` green. Each commit
is a candidate chained-PR slice per `work-unit-commits`.

---

## PR 1 — core + tests (Theme A + Theme B helpers + Theme C locale)

**Base**: `main` → **Target**: `main` (gates PR 2 + PR 3)
**Acceptance**: S2, S3, S8, S10, S15 (locale); `pytest -q` green ≥ 20 tests.

### T1.1 — Add dev dependencies [x]
- Type: `chore(deps)`
- Files: `requirements-dev.txt` (new), `requirements.txt` (unchanged)
- LoC: +5
- Commit: `chore(deps): add pytest + requests-mock to requirements-dev.txt`
  ```
  Add pytest>=7, pytest-cov>=4, requests-mock>=1.10 as dev-only deps.
  Runtime requirements.txt is unchanged.
  ```
- Acceptance: `pip install -r requirements-dev.txt` succeeds in venv.

### T1.2 — Bootstrap pytest harness [x]
- Type: `chore(ci)`
- Files: `pytest.ini` (new), `tests/__init__.py` (new), `tests/conftest.py` (new), `tests/test_smoke.py` (new)
- LoC: +60
- Commit: `chore(ci): bootstrap pytest harness (pytest.ini, conftest, smoke test)`
  ```
  Add pytest.ini with testpaths=tests. Add conftest with tmp_path fixture
  and monkeypatch of core.CACHE_DB / core.STATE_FILE. Add test_smoke.py
  asserting pytest itself is wired. NOT test-first per cached decision 3A.
  ```
- Acceptance: `pytest -q` runs and reports 1 passing smoke test.

### T1.3 — Failing tests for Theme A behavior [x]
- Type: `test` (TDD RED)
- Files: `tests/test_core.py` (new), `tests/test_locale.py` (new)
- LoC: +200
- Commit: `test(core): add failing tests for normalize falsy-zero, retry FetchError, cache CRUD, locale`
  ```
  Tests must FAIL on current core.py:
  - _normalize_item with compra=0 returns 0.0
  - _get_with_retry 5xx-after-3 raises FetchError(kind="http_5xx")
  - _get_with_retry network failure raises FetchError(kind="network")
  - _get_with_retry 404 returns [] (not an error)
  - cache_get / cache_put / cache_clear CRUD against tmp_path DB
  - fetch_range cache-hit short-circuit: time.sleep not called
  - MONTHS_ES[1] == "Enero", MONTHS_ABBR_ES[1] == "Ene"
  - import core does NOT create app data dir (monkeypatch path)
  ```
- Acceptance: `pytest -q tests/test_core.py tests/test_locale.py` exits non-zero with the listed failures.

### T1.4 — Introduce `FetchError` typed error class [x]
- Type: `feat(core)`
- Files: `core/errors.py` (new), `core/__init__.py` or `core.py` (re-export)
- LoC: +30 / -2
- Commit: `feat(core): introduce FetchError and typed error contract`
  ```
  Create core/errors.py with FetchError(Exception) carrying
  kind in {network, http_4xx, http_5xx, parse} and optional status.
  Re-export from core for from core import FetchError.
  ```
- Spec: data-fetch R1 (typed FetchError)
- Acceptance: T1.3 FetchError-kind tests now import-resolve; still red until T1.5.

### T1.5 — Rewrite `_get_with_retry` to raise `FetchError` + jitter [x]
- Type: `feat(core)`
- Files: `core.py` (modify `_get_with_retry`)
- LoC: +30 / -20
- Commit: `feat(core): _get_with_retry raises FetchError on persistent failure; add jitter`
  ```
  Replace silent [] collapse with typed FetchError per kind. Add
  random.uniform(0, delay) jitter to backoff sleeps. 404/204 still
  returns []. S3 covered.
  ```
- Spec: data-fetch R1 (S3)
- Acceptance: T1.3 retry tests now GREEN.

### T1.6 — Cache-hit short-circuit + lazy `_ensure_app_data_dir` [x]
- Type: `feat(core)`
- Files: `core.py` (modify `fetch_range`, `_app_data_dir`, `_connect`)
- LoC: +15 / -10
- Commit: `feat(core): cache-hit short-circuit in fetch_range; lazy mkdir in _connect`
  ```
  Track network_happened per month iteration; skip trailing
  time.sleep(0.3) when month served from cache. Move mkdir from
  _app_data_dir() into _ensure_app_data_dir() called from _connect().
  S2 and S10 covered.
  ```
- Spec: data-fetch R2 (S2) + R4 (S10)
- Acceptance: T1.3 cache-hit and import-side-effect tests GREEN.

### T1.7 — `_normalize_item` falsy-zero fix [x]
- Type: `feat(core)`
- Files: `core.py` (modify `_normalize_item`)
- LoC: +5 / -3
- Commit: `feat(core): preserve numeric 0 in _normalize_item`
  ```
  Replace compra = item.get("compra") or item.get("buyPrice") with
  explicit is None check. Same for venta. S8 covered.
  ```
- Spec: data-fetch R3 (S8)
- Acceptance: T1.3 falsy-zero test GREEN.

### T1.8 — `core/locale.py` + `core/validators.py` [x]
- Type: `feat(core)`
- Files: `core/locale.py` (new), `core/validators.py` (new), `core.py` (re-exports + wire `MONTHS_ABBR_ES` into `fetch_range` progress)
- LoC: +80
- Commit: `feat(core): MONTHS_ES locale and validate_range/validate_month helpers`
  ```
  Add core/locale.py with MONTHS_ES / MONTHS_ABBR_ES (13-element,
  index 0 unused). Add core/validators.py with validate_range and
  validate_month returning tuple | str. Replace calendar.month_abbr
  usage in core.fetch_range progress with MONTHS_ABBR_ES[m]. S15
  partial (locale defined; GUI call site is T3.x).
  ```
- Spec: localization R1+R2 (S15 partial) + input-validation R1+R2 (helpers)
- Acceptance: `pytest -q` green; `grep -n calendar.month_abbr core.py` returns 0 matches.

### T1.9 — Flip `strict_tdd: true` in openspec/config.yaml [x]
- Type: `docs`
- Files: `openspec/config.yaml`
- LoC: +5 / -3
- Commit: `docs: flip strict_tdd: true and populate test_command in openspec/config.yaml`
  ```
  strict_tdd: true, apply.tdd: true, apply.test_command: pytest -q,
  verify.test_command: pytest -q. Honors cached decision 3A.
  ```
- Spec: (config; supports all)
- Acceptance: `pytest -q` exits 0.

### Work-unit check (end of PR 1)
- [x] Every commit above leaves `pytest -q` green.
- [x] Total added LoC <= 400; if > 400, orchestrator triggers 4-PR fallback. **TRIGGERED**: 515 added / 19 deleted = 496 net (>400). 4-PR fallback engaged.
- [x] No CLI or GUI import-time change (CLI/GUI remain runnable against new `core`).
- [x] `grep -n _cancelled app.py` still 2 matches (will be removed in PR 3).
- [x] `grep -n calendar.month_abbr core.py` returns 0 matches (T1.8 done).
- [x] `from core import FetchError, validate_range, validate_month, MONTHS_ES, MONTHS_ABBR_ES` works.

---

## PR 2 — cli (validators + BOM + lazy openpyxl + typed errors)

**Base**: `main` (after PR 1 merges) → **Target**: `main`
**Acceptance**: S5, S6, S7; CSV first 3 bytes == `EF BB BF`; `--help` omits `--csv-bom`.

### T2.1 — Failing CLI tests [x]
- Type: `test` (TDD RED)
- Files: `tests/test_cli.py` (new)
- LoC: +90
- Commit: `test(cli): add failing tests for --range/--month validation, CSV BOM, --help`
  ```
  Tests must FAIL on current cli.py:
  - cli.run(['--range', '2025-01-01:2099-01-01']) exits 2 with Spanish
    stderr; fetch_range never called
  - cli.run(['--month', '1900', '1']) exits 2 with Spanish stderr
  - cli.run(['--csv', tmp_path/'o.csv']) writes EF BB BF as first 3 bytes
  - '--csv-bom' (or equivalent) NOT present in --help output
  ```
- Acceptance: `pytest -q tests/test_cli.py` exits non-zero; failures match the 4 scenarios.

### T2.2 — Wire `validate_range` / `validate_month` into `cli.run` [x]
- Type: `refactor(cli)`
- Files: `cli.py` (replace inline range/month validation)
- LoC: +25 / -30
- Commit: `refactor(cli): wire core.validate_range and core.validate_month`
  ```
  Replace inline range/month validation in cli.run with
  from core import validate_range, validate_month. On str return,
  print to stderr and return 2. S5 and S6 covered.
  ```
- Spec: input-validation R3 (S5, S6)
- Acceptance: T2.1 validation tests GREEN; S5 + S6 scenarios pass.

### T2.3 — Map `FetchError` to Spanish stderr messages [x]
- Type: `feat(cli)`
- Files: `cli.py` (wrap `core.fetch_*` calls in `try/except FetchError`)
- LoC: +20 / -10
- Commit: `feat(cli): map FetchError to Spanish stderr messages`
  ```
  Catch FetchError from fetch_day/fetch_month/fetch_range; map
  kind to a user-friendly Spanish message printed to stderr; return
  non-zero exit. Replaces bare except Exception. Honors localization
  R4 (Spanish user-facing; class name FetchError stays English).
  ```
- Spec: data-fetch R1 (callers see typed error) + localization R4
- Acceptance: stub `fetch_range` to raise `FetchError(kind="http_5xx")`; `cli.run(...)` exits non-zero with Spanish message on stderr.

### T2.4 — CSV `utf-8-sig` + lazy `openpyxl` in `_save_xlsx` [x]
- Type: `feat(cli)`
- Files: `cli.py` (change `_save_csv` encoding; move `openpyxl` import into `_save_xlsx`)
- LoC: +5 / -5
- Commit: `feat(cli): csv with utf-8-sig BOM; lazy openpyxl in _save_xlsx`
  ```
  Change _save_csv open(..., 'w', encoding='utf-8') to encoding='utf-8-sig'.
  Remove top-of-file `from openpyxl import ...`; import inside _save_xlsx.
  S7 and S11 (CLI half) covered.
  ```
- Spec: csv-export R1+R2 (S7) + app-startup-and-imports R1 (CLI half, S11)
- Acceptance: T2.1 BOM test GREEN; `--help` has no `--csv-bom`; first 3 bytes of produced CSV == `EF BB BF`.

### Work-unit check (end of PR 2)
- [x] Every commit above leaves `pytest -q` green.
- [x] Total added LoC <= 400 (PR 2 budget ~150). Actual: ~225 added / ~5 deleted = ~220 net (cli.py +45, tests/test_cli.py +180).
- [x] `grep -n 'encoding="utf-8"' cli.py` returns 0 matches inside `_save_csv`.
- [x] `grep -n '^from openpyxl' cli.py` returns 0 matches; only inline `import openpyxl` inside `_save_xlsx`.
- [x] `python app.py --help` exits 0; output contains no `--csv-bom`.

---

## PR 3 — app (cancel + token + status + startup hygiene)

**Base**: `main` (after PR 2 merges) → **Target**: `main`
**Acceptance**: S1, S4, S9, S11 (app half), S12, S13, S14, S15 (GUI half); manual smoke.

### T3.1 — Remove dead `_cancelled` field
- Type: `refactor(app)` **[x]**
- Files: `app.py` (remove `self._cancelled = False` lines at :194 and :586)
- LoC: +0 / -3
- Commit: `refactor(app): remove dead _cancelled field`
  ```
  Delete the two write-only assignments to self._cancelled. S1 covered.
  No behavior change.
  ```
- Spec: gui-worker-lifecycle R1 (S1)
- Acceptance: `grep -n '_cancelled' app.py` returns 0 matches; GUI starts and runs a fetch normally.

### T3.2 — Introduce `_worker_token` and `_cancel_event`
- Type: `feat(app)` **[x]**
- Files: `app.py` (add fields in `__init__`; check token at top of `_update` and `_on_fetch_done`)
- LoC: +20 / -5
- Commit: `feat(app): introduce _worker_token and cancel Event`
  ```
  Add self._worker_token: int = 0 and self._cancel_event = threading.Event()
  to __init__. Increment token and clear event at the top of _on_fetch
  before Thread.start(). _update closure captures token; if mismatched
  with self._worker_token, return silently. S4 partial.
  ```
- Spec: gui-worker-lifecycle R3 (S4 partial)
- Acceptance: synthetic stale callback (manually fire `_on_fetch_done` with stale rows) is dropped; no table touch, no status change.

### T3.3 — `Cancelar` button + quick-filter message
- Type: `feat(app)` **[x]**
- Files: `app.py` (add `Cancelar` button; wire `_on_cancel` to `_cancel_event.set()`; worker checks event between `fetch_*`; quick-filter path shows Spanish message)
- LoC: +60 / -15
- Commit: `feat(app): Cancelar button wired to cancel event + quick-filter message`
  ```
  Add Cancelar button next to Consultar; visible only while worker is
  alive. Click handler sets self._cancel_event and shows "Cancelando…"
  status. _fetch_worker checks the event between fetch_day/fetch_month/
  fetch_range and after each on_progress; on set, calls
  on_done([], "Consulta cancelada.") and returns. _on_fetch called
  while a worker is alive shows "Espere a que termine la consulta." in
  the status bar and returns early. NO auto-cancel, NO auto-restart.
  S4 complete, S14 covered. Honors cached decision 2A.
  ```
- Spec: gui-worker-lifecycle R2 (S4, S14)
- Acceptance: launch a long fetch; click `Cancelar` → status shows "Cancelando…" then "Consulta cancelada."; click quick-filter mid-fetch → "Espere a que termine la consulta." appears, no new thread starts.

### T3.4 — Status bar color constants + neutral "Sin datos"
- Type: `feat(app)` **[x]**
- Files: `app.py` (add `_COLOR_INFO/_COLOR_OK/_COLOR_NEUTRAL` constants; route all `_set_busy` calls through them)
- LoC: +20 / -10
- Commit: `feat(app): status bar color taxonomy (info/ok/neutral)`
  ```
  Add _COLOR_INFO = "#1f6feb", _COLOR_OK = "#2da44e", _COLOR_NEUTRAL = "#555"
  at module top. _set_busy(True, ...) uses INFO; success uses OK; empty
  result, "Caché borrado.", "No se encontraron datos…" use NEUTRAL.
  S12 covered.
  ```
- Spec: gui-worker-lifecycle R4 (S12)
- Acceptance: empty result paints neutral gray, not green; success paints green; busy paints blue.

### T3.5 — `geometry` TclError fallback to `850x600`
- Type: `feat(app)` **[x]**
- Files: `app.py` (wrap `self.root.geometry(...)` in `try/except tk.TclError`; persist fallback)
- LoC: +10 / -3
- Commit: `feat(app): geometry TclError fallback with 850x600`
  ```
  Wrap root.geometry(state.get("geometry", "850x600")) in try/except
  tk.TclError; on error, root.geometry("850x600") and re-persist to
  self.state so next launch is clean. S9 covered.
  ```
- Spec: app-startup-and-imports R2 (S9)
- Acceptance: corrupt `state.json` geometry → window opens at 850x600, no traceback, state.json updated.

### T3.6 — Lazy `openpyxl` in `_export_excel` + `_abrir_carpeta` helper
- Type: `feat(app)` **[x]**
- Files: `app.py` (remove top-of-file `from openpyxl import ...`; import inside `_export_excel`; new `_abrir_carpeta(path) -> bool`; refactor 2 `os.startfile` call sites)
- LoC: +40 / -15
- Commit: `feat(app): lazy openpyxl in _export_excel; _abrir_carpeta helper for os.startfile`
  ```
  Move `from openpyxl import Workbook, ...` into _export_excel as the
  first statement. Add SunatTCApp._abrir_carpeta(path) -> bool that
  calls os.startfile and on OSError logs WARNING and shows
  messagebox.showerror in Spanish. Refactor both os.startfile call
  sites (cache-info and export-complete) to use it. S11 (app half)
  and S13 covered.
  ```
- Spec: app-startup-and-imports R1 (app half, S11) + R3 (S13)
- Acceptance: `python -c "import sys, app; assert 'openpyxl' not in sys.modules"` exits 0; OSError on folder open triggers messagebox.showerror + WARNING log line.

### T3.7 — README note re: CSV BOM (Excel-friendly; JSON unaffected)
- Type: `docs` **[x]**
- Files: `README.md`
- LoC: +8 / -2
- Commit: `docs: README documents CSV BOM and JSON exemption`
  ```
  Add a short section explaining that --csv writes a UTF-8 BOM
  (Excel-friendly on Windows). Note that --json output is unaffected
  and `python app.py --json | jq ...` continues to work. Reference
  cached product decision 1A.
  ```
- Spec: csv-export R1 (user-facing docs)
- Acceptance: `grep -n BOM README.md` returns the new paragraph.

### Work-unit check (end of PR 3)
- [x] Every commit above leaves `pytest -q` green.
- [x] Total added LoC <= 400 (PR 3 budget ~300). Implementation (app.py + README, excluding tests): ~+144 LoC; test_app.py is +373 LoC and is outside the implementation budget per the work-unit-commits pattern (tests with behavior).
- [x] `grep -n _cancelled app.py` returns 0 matches (T3.1 done). The only matches are `_Cancelled` (the new sentinel class, capital C).
- [x] `grep -n 'from openpyxl' app.py` returns 0 matches at column 0; `from openpyxl import ...` lives only inside `_export_excel` (lines ~884-886, T3.6 done).
- [x] `grep -n 'except Exception: pass' app.py` returns 0 matches; both `os.startfile` sites use `_abrir_carpeta` (T3.6 done).
- [x] `grep -n calendar.month_name app.py` returns 0 matches; uses `MONTHS_ES[params['month']]` (wired in T3.2/T3.3 work, since the cancel worker was refactored to use MONTHS_ES at the same time as the calendar import was being kept only for `monthrange`).
- [ ] Manual smoke: GUI start → fetch today → cancel mid-fetch → fetch month → export XLSX → export CSV all pass on Windows. **NOT EXECUTED BY AGENT** — this agent does not launch the GUI; orchestrator/user handles the manual smoke per the brief.

---

## Tail: Spec → Task → Success-Criterion Trace

| S# | Finding | Spec | PR | Tasks | Test |
|----|---------|------|----|-------|------|
| S1 | Dead `_cancelled` | gui-worker-lifecycle R1 | 3 | T3.1 | `grep -n '_cancelled' app.py` returns 0 |
| S2 | Unconditional `time.sleep` | data-fetch R2 | 1 | T1.6 | `test_fetch_range_cache_hit_skips_sleep` |
| S3 | `_get_with_retry` swallows errors | data-fetch R1 | 1 | T1.4, T1.5 | `test_retry_5xx_raises`, `test_retry_network_raises`, `test_retry_404_returns_empty` |
| S4 | No GUI cancel path | gui-worker-lifecycle R2+R3 | 3 | T3.2, T3.3 | manual smoke + stale-callback drop test |
| S5 | `--range` no end bound | input-validation R1 | 2 | T2.2 | `test_cli_range_future_end_exits_2` |
| S6 | `--month` no year bound | input-validation R2 | 2 | T2.2 | `test_cli_month_below_min_year_exits_2` |
| S7 | CSV no BOM | csv-export R1 | 2 | T2.4 | `test_csv_first_bytes_are_bom` |
| S8 | `or` falsy-zero | data-fetch R3 | 1 | T1.7 | `test_normalize_preserves_zero_compra` |
| S9 | `geometry` TclError | app-startup-and-imports R2 | 3 | T3.5 | `test_geometry_tclerror_falls_back` (monkeypatch geometry to throw) |
| S10 | `mkdir` import side effect | data-fetch R4 | 1 | T1.6 | `test_import_core_does_not_create_app_data_dir` |
| S11 | Eager `openpyxl` (app+cli) | app-startup-and-imports R1 | 2+3 | T2.4, T3.6 | `test_import_app_does_not_load_openpyxl`, same for cli |
| S12 | "Sin datos" painted green | gui-worker-lifecycle R4 | 3 | T3.4 | `test_empty_result_uses_neutral_color` (monkeypatch _set_busy) |
| S13 | `os.startfile` swallowed | app-startup-and-imports R3 | 3 | T3.6 | `test_abrir_carpeta_raises_messagebox_on_oserror` (monkeypatch os.startfile) |
| S14 | Quick-filter during worker | gui-worker-lifecycle R2 | 3 | T3.3 | `test_quick_filter_during_worker_shows_espera` |
| S15 | English month names | localization R1+R2+R3 | 1+3 | T1.8, T3.6 | `test_fetch_range_progress_uses_spanish_abbr`, `test_gui_progress_uses_spanish_full` |

## Tail: Open Questions

None. All 4 product decisions are cached and honored in the task descriptions
above (1A BOM-default, 2A explicit-cancel-only, 3A strict-tdd-from-T1.3, 4A
Spanish UI / English class names).

## Tail: References

- Engram `#1879` — Judgment Day Round 1 synthesis (15 findings).
- Engram `#1882` — exploration report (5 themes, pre-work recommendation).
- Engram `#1883` — proposal executive summary.
- Engram `#1884` — spec index (6 specs, 15/15 acceptance coverage).
- Engram `#1885` — design exec summary (15 decisions, 3-PR chain).
- `openspec/AGENTS.md` — project conventions (Spanish UI, ISO dates, pathlib).
- `openspec/config.yaml` — `apply.chained_pr_strategy: ask-always`, `apply.review_budget: 400`.
