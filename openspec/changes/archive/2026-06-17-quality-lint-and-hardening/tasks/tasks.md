# Tasks: quality-lint-and-hardening (Change G)

> Apply order is fixed: **Q2 → Q7 → Q8 → Q1 (lint final)**. Q1 lints the FINAL
> code state, so all behavior/test edits land before the ruff pass. Strict TDD
> (`config.yaml: strict_tdd: true`). Test runner:
> `.\venv\Scripts\python.exe -m pytest -q`.

## Review Workload Forecast

- **Estimated net LoC**: ~120 (additions + deletions).
- **400-line budget risk**: Low (~120 << 400).
- **Chained PRs recommended**: No — single PR.
- **Decision needed before apply**: No.
- **One work unit per commit**: RED + GREEN pairs co-located; Q7 one commit; Q1 one commit.

## Phase 1 — Q2: FetchError kind validation

### T1.1 RED — Q2 test + rewrite the broken fallback test
- [x] Add `test_fetch_error_invalid_kind_raises_valueerror` to `tests/test_core.py`:
      `with pytest.raises(ValueError): FetchError("bogus")`. Confirm it FAILS
      (constructs silently today).
- [x] Rewrite `tests/test_messages.py:91-103`
      `test_format_fetch_error_unknown_kind_fallback` to build the instance via
      `FetchError.__new__(FetchError)` + set `.kind="alien_invasion"` +
      `.status=None` + `Exception.__init__(exc, "raw text")` (design D2).
      Confirm the rewritten test still PASSES against current production (the
      fallback branch is still covered). This is the mandatory companion to T1.2.

### T1.2 GREEN — Q2 validation
- [x] `core/errors.py:17-20`: add
      `if kind not in self.kinds: raise ValueError(f"Invalid FetchError kind {kind!r}; must be one of {self.kinds}")`
      BEFORE `super().__init__` (design D2).
- [x] Run `pytest -q` — `test_fetch_error_invalid_kind_raises_valueerror` now
      GREEN; the rewritten fallback test still GREEN; all 80 stay green.
- [ ] Commit: "Q2: validate FetchError kind at construction (+ rewrite fallback test)".

## Phase 2 — Q7: GUI test fixture isolation

### T2.1 GREEN — Q7 Toplevel-per-test fixture (no RED; existing 80 tests = proof)
- [x] `tests/test_app.py:53-71`: convert the `app` fixture to a generator that
      builds `toplevel = tk.Toplevel(hidden_root)`, `application =
      SunatTCApp(toplevel)`, `yield application`, then `toplevel.destroy()` in
      teardown (design D3). Keep `hidden_root` (lines 32-50) UNCHANGED.
- [x] Leave `test_geometry_tclerror_falls_back` (~158-195) on `hidden_root`
      (it monkeypatches `tk.Tk.geometry`, which does not affect `Toplevel`).
- [x] Run `pytest -q` IMMEDIATELY — all 80 tests must stay green. If a Tk test
      fails, suspect event-drain timing (`hidden_root.update()` vs
      `Toplevel.after`); fix with `toplevel.update()` in the draining test.
- [ ] Commit: "Q7: isolate GUI tests on a per-test Toplevel + teardown".

## Phase 3 — Q8: centralized `__version__` + `--version`

### T3.1 RED — Q8 tests
- [x] Add `test_core_has_version` to `tests/test_core.py`:
      `assert core.__version__ == "1.0.0"`. Confirm FAILS (no `__version__` yet).
- [x] Add `test_cli_version_flag_exits_0` to `tests/test_cli.py`: invoke
      `cli.run(["--version"])` (or `cli.main`), assert `SystemExit` code 0 and
      captured stdout contains `"1.0.0"`. Confirm FAILS (no `--version` yet).
- [x] Strengthen `tests/test_app.py::test_show_about_displays_version`
      (~767-789) to assert `core.__version__ in message` instead of the literal
      `"1.0.0"`. Confirm it still reflects intent (may pass/fail depending on
      current assertion — note the state).

### T3.2 GREEN — Q8 version wiring
- [x] `core/__init__.py`: add `__version__ = "1.0.0"` after the imports block
      (~line 31, before re-exports).
- [x] `app.py:41-57`: add `__version__` to the `from core import (...)` block.
- [x] `app.py:86-88`: DELETE the `_APP_VERSION` block.
- [x] `app.py:632`: replace `{_APP_VERSION}` with `{__version__}` in `_show_about`.
- [x] `cli.py:32-44`: add `__version__` to the `from core import (...)` block.
- [x] `cli.py` `_build_parser`: add `p.add_argument("--version",
      action="version", version=f"%(prog)s {__version__}")` (design D4).
- [x] Run `pytest -q` — the Q8 RED tests now GREEN; all 80 stay green.
- [ ] Commit: "Q8: centralize __version__ in core + add cli --version (+ remove _APP_VERSION)".

## Phase 4 — Q1: ruff linter (lint the FINAL state)

### T4.1 GREEN — Q1 ruff setup + findings (no RED; gate = `ruff check .` clean)
- [x] `requirements-dev.txt`: append `ruff>=0.6.0`.
- [x] Install: `.\venv\Scripts\python.exe -m pip install ruff`.
- [x] Create `ruff.toml` (standalone): `target-version = "py39"`,
      `line-length = 100`, `[lint] select = ["E", "F", "W", "I", "UP", "B", "SIM"]`
      (design D1).
- [x] Run `ruff check --fix` for SAFE fixes (UP035 import paths at `app.py:35`
      and `core/__init__.py:28` → `collections.abc`; isort). Review the diff.
- [x] Resolve `E501` at `app.py:1124` (114-char `askyesno` line) by reformat.
- [x] For any residual non-trivial finding: `# noqa: <code>  # <reason>`.
      Do NOT relax the rule set to hide noise.
- [x] `openspec/config.yaml:23`: set
      `linter: { available: true, command: "ruff check ." }`.
- [x] Run `ruff check .` — MUST exit 0.
- [ ] Commit: "Q1: add ruff linter + ruff.toml + fix/noqa findings (final-state gate)".

## Phase 5 — Verify

### T5.1 VERIFY — full gate
- [x] Run `.\venv\Scripts\python.exe -m pytest -q` — GREEN (80 existing + new
      Q2 `test_fetch_error_invalid_kind_raises_valueerror` + new Q8
      `test_core_has_version` / `test_cli_version_flag_exits_0`; rewritten
      unknown-kind-fallback test green).
- [x] Run `ruff check .` — exits 0 over the final code state.
- [x] Confirm `openspec/config.yaml` `testing.quality.linter.available == true`.
- [x] Confirm `app.py` no longer defines `_APP_VERSION`; `core.__version__ ==
      "1.0.0"`; `cli.py --version` prints `1.0.0` and exits 0.
- [x] Confirm spec deltas are in place (`app-startup-and-imports`,
      `data-fetch`, `none.md`) for the archive step.

## Notes

- **Commit grouping**: T1.1+T1.2 one commit; T2.1 one commit; T3.1+T3.2 one
  commit; T4.1 one commit. (RED + GREEN co-located per `work-unit-commits`.)
- **No git operations in this planning session** — tasks are executed by
  `sdd-apply`; commits happen at apply time.
- **Out of scope**: mypy, formatter, any A–F item, widening `root: tk.Tk`.
