# Verify Report: fix-gui-lifecycle-bugs (Change B)

## Goal

Verify the `fix-gui-lifecycle-bugs` change against its spec acceptance
criteria, design decisions (D1-D3), and task completion, with runtime
test evidence in strict TDD mode. The change fixes three GUI lifecycle
/ consistency defects: a stale `DEFAULT_STATE` geometry literal (B5), a
close-without-cancel race that could raise a silent `TclError` in the
worker thread (B6), and a hardcoded `730` range cap in the GUI that
could drift from `core.validators.MAX_RANGE_DAYS` (B7).

## Test Run Evidence

Command: `.\venv\Scripts\python.exe -m pytest -q`

```
...............................................................            [100%]
63 passed in 2.61s
```

- Baseline (post-Change-A): 57 tests.
- New RED-first tests added by Change B: 6.
- Total: 63 passed, 0 failed, 0 skipped.
- No warnings introduced by the new tests.

## Spec Acceptance Matrix

### Delta: `app-startup-and-imports` — 1 ADDED requirement, 1 scenario

| Scenario | Implementing code | Covering test | Status |
|---|---|---|---|
| First launch with no `state.json` -> window opens at `850x600` AND persisted geometry is `"850x600"` | `core/__init__.py:438` (`DEFAULT_STATE["geometry"] = "850x600"`); `app.py:221` fallback already `"850x600"`; `app.py:227` `minsize(850, 600)` | `tests/test_core.py::test_default_state_geometry_is_850x600` | **PASS** |

### Delta: `gui-worker-lifecycle` — 1 ADDED requirement, 2 scenarios

| Scenario | Implementing code | Covering test | Status |
|---|---|---|---|
| Close during an in-flight fetch -> `_cancel_event` set, worker joined (bounded) BEFORE `root.destroy()`, no `TclError`, state persisted | `app.py:526-528` (`self._cancel_event.set()`; `if self.worker and self.worker.is_alive(): self.worker.join(timeout=2.0)`) before `save_state`/`destroy` at `:529+` | `tests/test_app.py::test_on_close_sets_cancel_event`; `tests/test_app.py::test_on_close_joins_worker_before_destroy` | **PASS** |
| Worker stuck on slow network -> join times out, `save_state` and `root.destroy()` still execute, close does not hang (daemon thread) | `app.py:527-528` (bounded `join(timeout=2.0)`; worker is daemon per `app.py:687`) | `tests/test_app.py::test_on_close_destroy_still_happens_on_join_timeout` | **PASS** |

### Delta: `input-validation` — 1 MODIFIED requirement, 3 scenarios (2 retained + 1 new)

| Scenario | Implementing code | Covering test | Status |
|---|---|---|---|
| CLI rejects future end-date (retained) | `cli.py` `--range` path calls `validate_range` | `tests/test_cli.py::test_cli_range_future_end_exits_2` (pre-existing) | **PASS** |
| GUI rejects out-of-range year (retained) | `app.py:668-669` uses `MIN_YEAR`/`max_year()` | `tests/test_app.py` (pre-existing T3.x tests) | **PASS** |
| GUI range cap uses the canonical `MAX_RANGE_DAYS` (NEW) | `core/__init__.py:39` re-exports `MAX_RANGE_DAYS`; `app.py:43` imports it; `app.py:662-663` uses it in comparison + f-string | `tests/test_core.py::test_max_range_days_reexported_from_core`; `tests/test_app.py::test_validate_inputs_uses_max_range_days` (monkeypatches `app.MAX_RANGE_DAYS=10`, asserts 20-day span rejected + message interpolates `10`) | **PASS** |

**Matrix coverage: 6/6 scenarios COMPLIANT = 100% direct.**

## Design Decisions Verification

| Decision | Implemented as designed? | Note |
|---|---|---|
| D1 — B5: trivial literal change to `"850x600"` | **Yes** | `core/__init__.py:438`. Zero behavioral risk; aligns persisted default with `minsize` and runtime fallback. |
| D2 — B6: `set -> join(2.0) -> save_state -> destroy` with rationale comment | **Yes** | `app.py:516-528`. Comment documents the race, the token-guard discard, the 2.0s bound, and the daemon-thread safety net. Ordering verified by `test_on_close_joins_worker_before_destroy`. |
| D3 — B7: re-export via `core` mirroring `MIN_YEAR` pattern | **Yes** | `core/__init__.py:39` (`from .validators import MAX_RANGE_DAYS, MIN_YEAR, ...  # noqa: F401`); `app.py:43` imports from `core`. Single source in `validators.py:17`. Source-grep guard in `test_max_range_days_reexported_from_core` confirms no second definition. |

**Design coherence: 3/3 decisions implemented as designed.**

## Task Completion

`openspec/changes/fix-gui-lifecycle-bugs/tasks/tasks.md`:

- [x] T1.1 RED — `test_default_state_geometry_is_850x600`
- [x] T1.2 GREEN — B5 `DEFAULT_STATE["geometry"]` -> `"850x600"`
- [x] T2.1 RED — 3 `_on_close` tests (cancel / order / timeout)
- [x] T2.2 GREEN — B6 cancel + join(2.0) in `_on_close`
- [x] T3.1 RED — `test_max_range_days_reexported_from_core` + `test_validate_inputs_uses_max_range_days`
- [x] T3.2 GREEN — B7 re-export + import + `_validate_inputs` usage
- [x] T4.1 VERIFY — `pytest -q` -> 63 passed

The three commit tasks (T1.3/T2.3/T3.3) are intentionally `[ ]` per the
hard user constraint "NO git operations" — the user handles git
manually. These are not implementation tasks and are not flagged.

**Task completion: 7/7 implementation tasks `[x]`.**

## Strict TDD Evidence (spot-checks)

| Test | Would it fail on pre-Change-B code? | Reasoning |
|---|---|---|
| `test_default_state_geometry_is_850x600` | **Yes** | Pre-B5 `DEFAULT_STATE["geometry"]` was `"720x600"`; the assertion `== "850x600"` fails. |
| `test_on_close_sets_cancel_event` | **Yes** | Pre-B6 `_on_close` did not call `self._cancel_event.set()`; `is_set()` would be False. |
| `test_on_close_joins_worker_before_destroy` | **Yes** | Pre-B6 `_on_close` never called `worker.join`; the ordering assertion (`join` before `destroy`) fails. |
| `test_validate_inputs_uses_max_range_days` | **Yes** | Pre-B7 `app` module had no `MAX_RANGE_DAYS` binding; monkeypatch with `raising=False` avoids AttributeError, but the comparison used literal `730`, so a 20-day span with cap=10 would NOT be rejected -> the assertion that the error is returned fails. |

**Strict TDD: 4/4 spot-checks confirm RED-first.**

## Deviations from Design

None — implementation matches `design.md` exactly. Two judgment calls
within the design's latitude:
1. B6 rationale comment uses the design-D2 intent verbatim.
2. B7 test uses a 20-day span + monkeypatched cap=10 (stronger than the
   brief's 800-day example: a 20-day span is NOT rejected by the
   literal-`730` code, so only the constant-driven check can produce the
   error — proving both the comparison AND the message read
   `MAX_RANGE_DAYS`).

## Out-of-Scope Leakage

None. Working-tree changes touch ONLY B5/B6/B7:
- No Change D items (README/AGENTS/config docs untouched in this change).
- No Change E items (cache_put batching, sleep tuning untouched).
- No Change F items (GUI polish: today_label refresh, Ctrl+A, sort,
  Acerca de, progressbar determinate — untouched).
- No Change G items (ruff, FetchError kind validation, __version__
  untouched).

Grep confirms: `720x600` -> 0 matches in the project; `> 730` literal
in `app.py` -> 0 matches; `MAX_RANGE_DAYS` defined once in
`validators.py:17` and re-exported once in `core/__init__.py:39`.

## Final Verdict

**PASS.**

- 63/63 tests passing (57 baseline + 6 new RED-first).
- 6/6 spec scenarios COMPLIANT (100% direct coverage).
- 3/3 design decisions implemented as designed.
- 7/7 implementation tasks complete.
- 4/4 strict-TDD spot-checks confirm RED-first.
- No deviations, no out-of-scope leakage.

**Ready for archive: YES.**
