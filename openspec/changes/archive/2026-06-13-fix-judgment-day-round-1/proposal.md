# Proposal: fix/judgment-day-round-1

## Intent

Address 15 real WARNING findings from Judgment Day Round 1 (Engram `#1879`) across `core.py`, `cli.py`, `app.py`, plus bootstrap a test harness so the fixes are verifiable. The app is functional for its primary use case; these fixes harden data-layer error propagation, parity between CLI and GUI validation, Windows-friendly encoding/i18n, GUI thread lifecycle, and resource-import hygiene.

## Scope

### In Scope
- All **15 real WARNING findings** (7 confirmed + 8 re-judged real) per Engram `#1879` / `#1882`.
- Bootstrap `pytest` + `requests-mock` + `tests/` as **Task 0** (gate for PR 1+).
- Flip `strict_tdd: true` in `openspec/config.yaml` from Task 1 onward.
- New typed errors from `_get_with_retry` (network / 4xx / 5xx / parse).
- Shared `validate_range` / `validate_month` helpers in `core.py` (eliminate CLI↔GUI drift).
- `MONTHS_ES` constant; CSV UTF-8-with-BOM default.
- GUI cancel button + generation token; remove dead `_cancelled`.
- Lazy `openpyxl` import; `geometry` TclError fallback; `os.startfile` logging.

### Out of Scope (deferred to a future change)
- **5 confirmed SUGGESTIONs** from the audit (polish; non-blocking; details to be itemized in a follow-up proposal when scope is re-estimated).
- A `--csv-bom` toggle — we commit to BOM-default-only in this cycle.
- Replacing the SQLite cache with a different backend.
- Refactoring the GUI to another framework (e.g. PySide).
- A new config file or env-var overrides surface.

## Capabilities

> Contract for `sdd-spec`. `openspec/specs/` is currently empty (Engram `#1880`), so every entry below becomes a **new full spec** (not a delta).

### New Capabilities
- **`data-fetch`**: HTTP retry, cache, normalization, and range/month fetch behavior with typed `FetchError` results.
- **`input-validation`**: shared `validate_range(start, end) -> tuple[date, date] | str` and `validate_month(year, month) -> tuple[int, int] | str` used by both CLI and GUI.
- **`csv-export`**: CSV writer produces UTF-8 with BOM (`utf-8-sig`) by default.
- **`localization`**: `MONTHS_ES` constant replaces `calendar.month_abbr` / `month_name` in user-visible contexts.
- **`gui-worker-lifecycle`**: cancel button, generation token (so stale `on_done` from a cancelled worker cannot overwrite a new query), status-bar color states (info/ok/error/empty), and quick-filter behavior while a worker is running.
- **`app-startup-and-imports`**: lazy `openpyxl` import, `geometry` TclError fallback to `850x600`, `os.startfile` log + `showerror` on failure (two call sites).

### Modified Capabilities
- **None** (no existing specs to modify).

## Approach

Split into **3 chained PRs** to fit the 400-line review budget (Engram `#1882`). Each PR is a reviewable work unit (per `work-unit-commits`).

1. **PR 1 — core + tests** (~350 lines). Bootstrap `pytest` (`pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`, `tests/test_core.py`). Fix Theme A: typed `FetchError` from `_get_with_retry`; `fetch_range` cache-hit short-circuit; `_normalize_item` `or` → explicit `is None`; move `mkdir` into `_ensure_app_data_dir()`. Add `validate_range` / `validate_month`. Add `MONTHS_ES`. Change `_save_csv` default to `utf-8-sig`.
2. **PR 2 — cli** (~150 lines). Wire `core.validate_range` / `validate_month` into `cli.run`; surface new typed errors to stderr with Spanish messages; use `MONTHS_ES`; lazy `openpyxl` import in `cli._save_xlsx`.
3. **PR 3 — app** (~300 lines). Theme D: explicit `Cancelar` button, `threading.Event` cancel, generation token checked at top of `_update`; status bar uses neutral color for "Sin datos"; quick-filter during a worker is either rejected or starts a new query. Theme E: lazy `openpyxl` in `_export_excel`; `try/except tk.TclError` around `self.root.geometry(...)`; `os.startfile` logs to stderr and shows `messagebox.showerror` on failure. Remove dead `_cancelled` field.

If PR 1 exceeds 400 lines after tests, split it into "bootstrap + Theme A" and "Theme B + C" (4 PRs total). Decision deferred to `sdd-tasks`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `core.py` | Modified | Theme A (errors, cache-hit, falsy-zero, lazy mkdir), Theme B (validation helpers), Theme C (`MONTHS_ES`, BOM default) |
| `cli.py` | Modified | Theme B (validation), Theme C (BOM consumed, `MONTHS_ES`), Theme E (lazy openpyxl), error mapping |
| `app.py` | Modified | Theme D (cancel/token/colors/quick-filter), Theme E (lazy import/geometry/os.startfile); remove dead `_cancelled` |
| `requirements.txt` | Modified | Unchanged runtime; dev deps move to `requirements-dev.txt` |
| `requirements-dev.txt` | New | `pytest>=7`, `pytest-cov>=4`, `requests-mock>=1.10` |
| `tests/` | New | `conftest.py` (tmp_path, mocked HTTP), `test_core.py` (normalize/coerce/retry/cache) |
| `pytest.ini` | New | `testpaths = tests` |
| `openspec/config.yaml` | Modified | `strict_tdd: true`, `apply.tdd: true`, `apply.test_command: pytest -q`, `verify.test_command: pytest -q` |
| `README.md` | Modified | Document CSV BOM and `--json | jq` exemption (JSON path unchanged) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| CSV BOM breaks Unix pipelines (`jq`, `awk`, `cut`) | Med | Documented in README. JSON output is unaffected. The 4 product-decision memo locked BOM as always-on; rollback is one-line. |
| Worker cancel race: late `on_done` from cancelled worker overwrites a new query | Med | Generation token (`self._worker_id += 1`) checked at top of `_update`; stale results discarded silently. Explicit `Cancelar` button only, no auto-cancel on quick-filter (decision 2A). |
| Type change to `_get_with_retry` breaks CLI `except Exception` swallowing | Med | Replace CLI's bare `except Exception` with explicit handling of the new typed errors; keep a top-level fallback. |
| Removing `mkdir` import-time side effect breaks callers expecting the dir to exist | Low | Move into `_ensure_app_data_dir()` called from the first cache function; covered by new tests. |
| PR 1 exceeds 400-line review budget with tests + Theme A + B + C | Med | Watch the line count; if exceeded, split into 2 PRs (4 total). |
| `geometry` TclError cannot be tested in headless CI | Low | Wrap in `try/except tk.TclError`; skip with a marker in tests that require a display. |
| Lazy `openpyxl` import paths missed in `app.py` | Low | Only `_export_excel` uses it (verified Engram `#1882`); import inside the function. |
| `os.startfile` is Windows-only | Low | Already lazy-conditional; add stderr log + `showerror` on any `OSError`. |
| `strict_tdd: true` flip blocks PR 1 if pytest bootstrap has gaps | Low | Task 0 lands with at least one smoke test passing; PR 1's test suite grows from there. |

## Rollback Plan

Per-PR revert via `git revert` (work-unit commits keep each PR to one concern). Layer isolation:
- **Theme A** changes live in `core.py`; revert restores the swallowing `_get_with_retry` and import-time `mkdir`.
- **Theme B/C** changes live in `core.py` helpers + `cli.py`; revert restores ad-hoc CLI validation and UTF-8-without-BOM CSV.
- **Theme D/E** changes live in `app.py`; revert restores dead `_cancelled` field, no cancel button, eager `openpyxl`, no `geometry` fallback, swallowed `os.startfile`.
- **Test bootstrap** (`tests/`, `pytest.ini`, `requirements-dev.txt`) is removable without touching source.
- **CSV BOM** is a one-line diff in `_save_csv`; reverting restores pre-change behavior.
- **No data migrations**: cache (`%APPDATA%\sunat-tc-app\cache.db`) and state (`state.json`) are append-only / forward-compatible.

## Dependencies

- **External API**: `apis.net.pe` (no key, undocumented rate limit) — unchanged.
- **Runtime deps** (unchanged): `requests>=2.31.0`, `openpyxl>=3.1.2`.
- **New dev deps** (Task 0): `pytest>=7`, `pytest-cov>=4`, `requests-mock>=1.10`.
- **Task 0 (pytest bootstrap) is a hard gate** for Tasks 1+ that change behavior in `core.py`.
- **No new runtime deps**; no DB schema changes; no API contract changes.

## Success Criteria (Acceptance)

Each row corresponds to one Judgment Day finding (Engram `#1879`). All MUST be verifiable after the change ships.

| # | Finding (file:line) | Given | When | Then |
|---|---------------------|-------|------|------|
| S1 | Dead `_cancelled` (app.py:194, :586) | GUI source | `grep -n '_cancelled' app.py` | zero matches |
| S2 | `fetch_range` sleep (core.py:336) | range fully cached | `fetch_range` runs | zero `time.sleep` calls; cached rows returned |
| S3 | `_get_with_retry` swallows errors (core.py:107-122) | API returns 5xx × 3 | call | raises `FetchError(kind="network")`, not `[]` |
| S4 | No GUI cancel path (app.py:579-593) | worker running | user clicks "Cancelar" | `_worker_id` increments; subsequent `_update` from old worker is dropped |
| S5 | `--range` no end bound (cli.py:204-218) | `--range 2025-01-01 2099-01-01` | CLI runs | exit code 2 + Spanish stderr message |
| S6 | `--month` no year bound (cli.py:219-229) | `--month 1900 1` | CLI runs | exit code 2 + Spanish stderr message |
| S7 | CSV no BOM (cli.py:115-120) | `--csv` run | inspect first 3 bytes | `EF BB BF` (UTF-8 BOM) |
| S8 | `or` falsy-zero (core.py:75-77) | API payload `compra=0` | `fetch_day` | returns `compra=0.0` (not `None`) |
| S9 | `geometry` TclError (app.py:188-189) | corrupt `state.json` geometry | app starts | falls back to `850x600`; no traceback |
| S10 | `mkdir` import side effect (core.py:60) | import `core` | trace / static check | no top-level `Path.mkdir` / `os.mkdir` |
| S11 | Eager `openpyxl` (app.py:33-35) | import `app` | no export triggered | no `openpyxl` import in `app.__dict__` |
| S12 | "Sin datos" green (app.py:546, :637-639) | empty result | status bar painted | neutral / info color, not success green |
| S13 | `os.startfile` swallowed (app.py:524, :821) | folder open fails | stderr / messagebox | WARNING line + `showerror` dialog |
| S14 | Quick-filter during worker (app.py:580-582) | worker running | user clicks quick-filter | explicit "Espere a que termine la consulta" message OR token-incremented new query |
| S15 | English `month_abbr`/`month_name` (core.py:319, app.py:628) | GUI/CLI month display | inspect strings | uses `MONTHS_ES` (e.g. `"Ene"`, `"Ene."`, `"Enero"`) |

**Aggregate**: `pytest -q` is green after PR 1; new test count ≥ 20 unit tests covering normalize, retry, cache, and validators; manual smoke test (GUI start → fetch today → cancel → fetch month → export XLSX → export CSV) passes on Windows.

## Delivery Plan

3 chained PRs (per Engram `#1882`, refined at `sdd-tasks`):

- **PR 1 — core + tests** (~350 lines): bootstrap pytest + Theme A + Theme B helpers + Theme C locale & BOM. Reviewable in isolation; gates downstream PRs.
- **PR 2 — cli** (~150 lines): wire new validators + new error types + lazy openpyxl into `cli.py`.
- **PR 3 — app** (~300 lines): Theme D (cancel/token/status/quick-filter) + Theme E (lazy import/geometry/os.startfile) into `app.py`. Remove dead `_cancelled`.

Fallback: if PR 1 exceeds 400 lines, split into "PR 1a: bootstrap + Theme A" and "PR 1b: Theme B + C" (4 PRs total). The user decides at PR-review time.

Each PR lands as multiple work-unit commits (per `work-unit-commits`): one concern per commit, tests co-located with the code they cover.

## Open Questions

**None.** The 4 product decisions are pre-resolved in the orchestrator brief (and captured as cached decisions):

1. **CSV BOM default**: always `utf-8-sig` (breaking change for Unix consumers — listed in Risks).
2. **Cancel behavior**: explicit `Cancelar` button wired to a real cancel flag; **no** auto-cancel on new quick-filter; **generation token required** so a late `on_done` from a cancelled worker cannot overwrite a new query.
3. **TDD discipline**: `strict_tdd: true` from Task 1 onward; Task 0 (pytest bootstrap) is not test-first.
4. **Language**: all user-facing strings in Spanish (GUI status bar, messageboxes, CLI stderr); exception class names in English (programmer convention).

No new product forks were identified during proposal drafting.

## References

- **Engram `#1879`** — Judgment Day Round 1 synthesis (15 findings, file:line, judge attributions).
- **Engram `#1880`** — sdd-init report (stack, module map, conventions, `strict_tdd: false`).
- **Engram `#1881`** — testing capabilities (no test runner; recommended bootstrap).
- **Engram `#1882`** — exploration report (5 themes, cross-cutting concerns, chained-PR flag, pre-work recommendation).
- `openspec/AGENTS.md` — project conventions (Spanish UI strings, ISO `YYYY-MM-DD` storage, `DD/MM/YYYY` GUI display, `pathlib.Path`).
- `openspec/config.yaml` — SDD schema, `strict_tdd: false` (flipped to `true` after Task 0), `apply.chained_pr_strategy: ask-always`, `apply.review_budget: 400`.
