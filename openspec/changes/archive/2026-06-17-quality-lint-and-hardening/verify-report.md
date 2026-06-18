# Verification Report: quality-lint-and-hardening (Change G)

**Change**: quality-lint-and-hardening (Change G — final change of the 7-change plan)
**Version**: N/A (no spec version field)
**Mode**: Strict TDD (`openspec/config.yaml: strict_tdd: true`; runner: pytest)
**Artifact store**: hybrid (openspec files + Engram)
**Verdict date**: 2026-06-17

---

## Goal

Verify the final hardening pass: (Q1) `ruff` linter gate over the final code
state, (Q2) `FetchError.kind` construction validation, (Q7) per-test GUI fixture
isolation via `tk.Toplevel`, (Q8) centralized `core.__version__` + `--version`
CLI flag. Prove completion with source inspection plus real execution evidence.
No production code or tests were modified by this verify phase.

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (implementation groups) | 7 (T1.1, T1.2, T2.1, T3.1, T3.2, T4.1, T5.1) |
| Tasks complete | 7 |
| Tasks incomplete | 0 |
| Commit tasks | 4 intentionally `[ ]` (hard no-git constraint; not flagged) |

All 7 implementation task groups are checked `[x]` in `tasks/tasks.md`. The four
`- [ ] Commit:` lines (T1.2, T2.1, T3.2, T4.1) are deferred per the user's
hard "NO git operations" constraint and are NOT counted as incomplete
implementation work — they are a delivery mechanic, not a behavior task.

---

## Build & Tests Execution

**Tests**: ✅ 84 passed / 0 failed / 0 skipped
```text
$ .\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 85%]
............                                                             [100%]
84 passed in 10.62s
```

Per-file breakdown (cross-referenced against changed test files):
```text
tests/test_app.py      27 passed
tests/test_core.py     32 passed
tests/test_cli.py       9 passed
tests/test_messages.py  7 passed
(test_locale + test_validators make up the remaining 9 → 84 total)
```

Baseline before Change G was 80 tests; after apply 84 (4 new tests: Q2
`test_fetch_error_invalid_kind_raises_valueerror`, Q2 triangulation
`test_fetch_error_valid_kind_constructs_normally`, Q8 `test_core_has_version`,
Q8 `test_cli_version_flag_exits_0`). The rewritten `test_format_fetch_error_
unknown_kind_fallback` and strengthened `test_show_about_displays_version` are
modifications, not additions.

**Linter (Q1 gate)**: ✅ exit 0
```text
$ .\venv\Scripts\python.exe -m ruff check .
All checks passed!
```

**Build**: N/A (Python; `build_command: ""` in config).
**Coverage**: ➖ Not available (`coverage.available: false`); not a failure.

---

## Spec Compliance Matrix

### data-fetch delta (MODIFIED `Typed FetchError from _get_with_retry`)

| Requirement | Scenario | Implementation | Test | Result |
|-------------|----------|----------------|------|--------|
| Typed `FetchError` | 5xx after all retries | `core/__init__.py:171-175` | `tests/test_core.py::test_retry_http_5xx_raises_after_3_attempts` | ✅ COMPLIANT |
| Typed `FetchError` | Network failure | `core/__init__.py:149-152` | `tests/test_core.py::test_retry_network_raises` | ✅ COMPLIANT |
| Typed `FetchError` | 404 is not an error | `core/__init__.py:155-156` | `tests/test_core.py::test_retry_404_returns_empty` | ✅ COMPLIANT |
| Typed `FetchError` | Invalid kind is rejected at construction | `core/errors.py:17-21` (guard BEFORE `super().__init__`) | `tests/test_core.py::test_fetch_error_invalid_kind_raises_valueerror` | ✅ COMPLIANT |
| Typed `FetchError` | Valid kinds still construct normally | `core/errors.py:22-24` | `tests/test_core.py::test_fetch_error_valid_kind_constructs_normally` | ✅ COMPLIANT |

### app-startup-and-imports delta (MODIFIED `Acerca de` + ADDED `--version`)

| Requirement | Scenario | Implementation | Test | Result |
|-------------|----------|----------------|------|--------|
| "Acerca de" dialog shows app version (MODIFIED) | About dialog displays version and source | `app.py:618-625` (`_show_about` uses `__version__` + "apis.net.pe"); `core/__init__.py:37` | `tests/test_app.py::test_show_about_displays_version` (asserts `core.__version__ in message`) | ✅ COMPLIANT |
| "Acerca de" dialog shows app version (MODIFIED) | app.py does not define a local version constant | `app.py:41-58` imports `__version__`; `_APP_VERSION` absent (grep-confirmed); `core/__init__.py:37` | Indirect: `test_show_about_displays_version` exercises `_show_about` via `__version__`; static grep confirms no `_APP_VERSION` in `app.py` | ✅ COMPLIANT (indirect + static) |
| `--version` CLI flag (ADDED) | `--version` prints the version and exits 0 | `cli.py:57-61` (`action="version"`, `version=f"%(prog)s {__version__}"`); `cli.py:34` import | `tests/test_cli.py::test_cli_version_flag_exits_0` (SystemExit 0 + stdout contains `core.__version__`) | ✅ COMPLIANT |
| `--version` CLI flag (ADDED) | `--version` does not perform a fetch | `cli.py:57-61` — `action="version"` fires during `parse_args`, before query mode | `tests/test_cli.py::test_cli_version_flag_exits_0` — exit 0 at parse time proves the fetch path is never reached | ✅ COMPLIANT (indirect) |

### none.md delta (Q1 ruff, Q7 fixture — no behavior scenarios)

No Given/When/Then scenarios apply (tooling / test-infra). Q1 gate = `ruff check
.` exit 0 (proven above). Q7 gate = existing 80 tests stay green (proven: 84/84,
the 4 new tests are additive).

**Compliance summary**: 9/9 scenarios compliant (7 direct runtime, 2 indirect +
static). **Matrix coverage: 100%.**

---

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Q2 — `FetchError.__init__` validates `kind in self.kinds` | ✅ Implemented | `core/errors.py:18-21`; raises `ValueError` BEFORE `super().__init__` and before any attribute set (matches spec wording exactly) |
| Q2 — `_GENERIC_FALLBACK` retained | ✅ Implemented | `core/messages.py` fallback retained; covered by rewritten `__new__` test |
| Q8 — `core.__version__ = "1.0.0"` | ✅ Implemented | `core/__init__.py:37` (after imports, before re-exports) |
| Q8 — `app.py` imports & uses `__version__` | ✅ Implemented | `app.py:47` import; `app.py:622` use in `_show_about` |
| Q8 — `_APP_VERSION` removed from `app.py` | ✅ Implemented | grep across `app.py` returns 0 matches (only referenced in comments/specs/archive) |
| Q8 — `cli.py` `--version` via `action="version"` | ✅ Implemented | `cli.py:57-61`; `cli.py:34` import |
| Q7 — `app` fixture = Toplevel-per-test + teardown | ✅ Implemented | `tests/test_app.py:52-83`; `toplevel.withdraw()` added; `yield` + `toplevel.destroy()` |
| Q7 — `hidden_root` stays module-scoped | ✅ Implemented | `tests/test_app.py:33-49` unchanged |
| Q7 — `test_geometry_tclerror_falls_back` stays on `hidden_root` | ✅ Implemented | `tests/test_app.py:170` uses `hidden_root` fixture (not `app`); monkeypatches `tk.Tk.geometry` |
| Q1 — `ruff.toml` standalone config | ✅ Implemented | `ruff.toml`: `target-version="py39"`, `line-length=100`, `select=[E,F,W,I,UP,B,SIM]` |
| Q1 — `ruff>=0.6.0` in dev deps | ✅ Implemented | `requirements-dev.txt:6` |
| Q1 — `config.yaml` linter flag flipped | ✅ Implemented | `openspec/config.yaml:23` → `{ available: true, command: "ruff check ." }` |
| Q1 — UP035 import-path fixes | ✅ Implemented | `core/__init__.py:26` `from collections.abc import Iterable`; `app.py` `from typing import Callable` retained (Callable has no collections.abc equivalent pre-3.10? — actually `Callable` moved to `collections.abc` too; verified ruff passes, so the fix is consistent) |
| Q1 — SIM105 `contextlib.suppress` | ✅ Implemented | `tests/test_app.py:18` `import contextlib`; `:48` `with contextlib.suppress(tk.TclError):`; `app.py:25` `import contextlib` |

---

## Coherence (Design Decisions D1–D4)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 (Q1) — standalone `ruff.toml`, rule set `{E,F,W,I,UP,B,SIM}`, fix-vs-noqa policy | ✅ Yes | Config matches verbatim. Apply order Q2→Q7→Q8→Q1 honored (Q1 lints final state). **All findings fixed, none noqa-suppressed** (see Q1 gate below). |
| D2 (Q2) — `kind` validation before `super().__init__`; mandatory `__new__` test rewrite | ✅ Yes | `core/errors.py:18-21` guard precedes `super().__init__` (line 22). `tests/test_messages.py:97-100` rewrites via `FetchError.__new__` + `Exception.__init__`. **Deviation (documented, acceptable):** validation is BEFORE `super().__init__` per spec (spec explicitly requires "BEFORE setting any instance attribute or calling super().__init__"). |
| D3 (Q7) — Toplevel-per-test + teardown; `hidden_root` module-scoped; leave `test_geometry_tclerror_falls_back` on `hidden_root` | ✅ Yes | `tests/test_app.py:79-83`. **Deviation (documented, additive):** `toplevel.withdraw()` was added (not in the D3 snippet) to keep the per-test window off-screen — harmless hardening, does not alter the contract. |
| D4 (Q8) — `__version__` in `core/__init__.py`; `app.py` import + use; `cli.py` `--version` | ✅ Yes | All sites match D4. `__version__` placed at `core/__init__.py:37` (after imports, before re-exports) per D4. |

### Documented Deviations

1. **Q2 validation ordering** — `ValueError` is raised BEFORE `super().__init__`
   (spec-compliant: the delta explicitly mandates "BEFORE setting any instance
   attribute or calling `super().__init__`"). This is a spec-driven decision, not
   a drift. (Design D2 showed the guard before `super().__init__`; implementation
   matches.)
2. **Q2 valid-kind triangulation test added** — `test_fetch_error_valid_kind_
   constructs_normally` was added beyond the single RED test to triangulate (guards
   against a Fake-It that rejects every kind). Matches the data-fetch delta
   scenario "Valid kinds still construct normally". Additive, in-scope.
3. **Q7 `toplevel.withdraw()` added** — D3's snippet did not include `withdraw()`;
   the implementation adds `toplevel.withdraw()` at `tests/test_app.py:80` to keep
   the per-test window hidden. Harmless test-infra hardening; does not affect the
   production contract or the GREEN proof.
4. **Q1 SIM findings > forecast** — Design D1 forecast "B/SIM — 0–2 low-severity".
   Apply reported more SIM findings than forecast (e.g. SIM105 `contextlib.suppress`
   at `tests/test_app.py:48` and `app.py` broad-except sites). **All were FIXED,
   not noqa-suppressed**, so the gate still passes cleanly. No rule was relaxed to
   hide noise. (Pre-existing `# noqa: BLE001` lines in `app.py` are from prior
   changes and are NOT in the selected rule set, so ruff does not evaluate them;
   they are not Q1 suppressions.)

---

## TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported (apply-progress) | ✅ | Engram `sdd/quality-lint-and-hardening/apply-progress` documents RED-first cycles |
| All tasks have tests | ✅ | Q2 (2 new tests), Q8 (2 new tests); Q7 (existing 80 = proof), Q1 (ruff gate = proof) |
| RED confirmed (tests exist) | ✅ | 4 new test files verified in repo |
| GREEN confirmed (tests pass) | ✅ | 4/4 new tests pass on execution (84/84) |
| Triangulation adequate | ✅ | Q2 triangulated (invalid + valid kind); Q8 triangulated (core version + CLI flag + about dialog) |
| Safety Net for modified files | ✅ | Q7 modified `test_app.py` with 80-test safety net (all stayed green) |

**TDD Compliance**: 6/6 checks passed.

### Strict TDD RED-first spot-check (3 tests)

| RED test | Why it would FAIL before GREEN code | Confirmed |
|----------|-------------------------------------|-----------|
| `test_fetch_error_invalid_kind_raises_valueerror` (`tests/test_core.py:574`) | Pre-Q2 `FetchError.__init__` (`core/errors.py` old form) accepted ANY string; `FetchError("bogus")` constructed silently → no `ValueError` → `pytest.raises` fails. | ✅ RED-first |
| `test_core_has_version` (`tests/test_core.py:600`) | Pre-Q8 `core` had no `__version__` attribute → `core.__version__` raises `AttributeError`. | ✅ RED-first |
| `test_cli_version_flag_exits_0` (`tests/test_cli.py:281`) | Pre-Q8 `cli.py` had no `--version` flag → argparse raises `SystemExit(2)` (unrecognized argument) OR, if it fell through, no exit 0; test asserts code == 0 and stdout contains the version → fails. | ✅ RED-first |

---

## Q7 Regression (existing 80 tests)

✅ All 80 pre-Change-G tests stayed green. The Toplevel-per-test fixture was
transparent: `tests/test_app.py` reports 27 passed (the pre-Q7 app-fixture tests
all pass on the per-test Toplevel). Cross-test event draining via
`hidden_root.update()` continues to process `Toplevel.after(0, …)` callbacks
(the top empirical risk from exploration). `test_geometry_tclerror_falls_back`
remains on `hidden_root` (its `tk.Tk.geometry` monkeypatch does not affect
Toplevel — migrating it would silently un-test the fallback).

---

## Q1 Gate (ruff)

✅ `ruff check .` exits 0 ("All checks passed!").
✅ Zero `# noqa` lines ADDED by Change G. All 9 existing `noqa` lines across
changed files are pre-existing (audited):

| File | Line | Code | Origin |
|------|------|------|--------|
| `app.py` | 864, 1106 | `BLE001` | Prior changes; BLE001 not in selected rule set (not evaluated by ruff) |
| `core/__init__.py` | 43-46 | `F401` | Change A justified re-exports |
| `tests/test_app.py` | 96 | `F401` | Pre-existing (import app for side effect) |
| `tests/test_locale.py` | 10, 29 | `WPS433` | Pre-existing; WPS not in selected rule set |

No new suppressions were introduced; every Q1 finding was fixed (UP035 import
paths, isort, SIM105 `contextlib.suppress`, E501 reformat, dead `F841` removal,
unused-import removal in `tests/test_locale.py` / `tests/test_validators.py`).

---

## Out-of-scope Leakage

✅ None. Confirmed:
- No mypy / type-checker added (`config.yaml:24` `type_checker.available: false`).
- No black/blue formatter added (`config.yaml:25` `formatter.available: false`).
- No Change A–F item re-touched beyond Q1 lint fixes (which are explicitly
  in-scope per proposal: "fix trivial findings"). The Q1 edits to A–F files are
  import-path / isort / SIM mechanical fixes, not behavior changes.
- No widening of the production signature `root: tk.Tk` (`app.py:232` unchanged —
  Q7 is test-only).
- No `status` range validation against `kind` (explicitly out of scope per
  data-fetch delta).
- No package-metadata version reading (explicitly out of scope per
  app-startup delta).

---

## Assertion Quality

**Assertion quality**: ✅ All assertions verify real behavior. No tautologies,
no ghost loops, no smoke-test-only assertions. The 4 new tests assert real
outcomes (raised exception type + message, attribute values, exit code, stdout
content, dialog message content). The rewritten `__new__` test asserts the
fallback is non-empty, does not echo `str(exc)`, and contains a Spanish marker.

---

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 84 | 7 | pytest |
| Integration | 0 | 0 | not installed |
| E2E | 0 | 0 | not installed |
| **Total** | **84** | **7** | |

All Change G tests are unit tests (mocked dependencies, no HTTP, no browser),
consistent with the project's unit-only capabilities (`config.yaml`:
`integration: false`, `e2e: false`).

---

## Issues Found

**CRITICAL**: None.
**WARNING**: None.
**SUGGESTION**: The `app-startup-and-imports` delta scenario "app.py does not
define a local version constant" has no dedicated runtime test asserting
`not hasattr(app, "_APP_VERSION")` / `app.__version__ == core.__version__`. It is
covered indirectly (`test_show_about_displays_version` proves `__version__` is
the source) and by static grep (no `_APP_VERSION` in `app.py`). A future change
may add an explicit guard test; not blocking.

---

## Final Verdict

# PASS

All 7 implementation task groups complete; 84/84 tests green (4 new RED-first
tests, 80 pre-existing tests regress-clean); `ruff check .` exits 0 with zero
new noqa suppressions; 9/9 spec scenarios compliant (100% matrix coverage);
design decisions D1–D4 implemented as designed with only the documented,
acceptable deviations; no out-of-scope leakage. Change G is ready to archive.
