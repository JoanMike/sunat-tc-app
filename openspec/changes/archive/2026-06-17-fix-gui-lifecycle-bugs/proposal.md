# Proposal: fix-gui-lifecycle-bugs

## Intent

The GUI layer has three small, independent defects that surface as a
lying persisted default geometry, a close-without-cancel race that raises a
silent `TclError` inside the worker thread, and a magic-number range cap that
can drift from the canonical `core.validators.MAX_RANGE_DAYS`. All three are
localized and verified (see `exploration.md`); the fix is ~110 LoC in a single
PR, RED-first per `config.yaml:9 strict_tdd: true`. Depends on Change A
(`max_year()`, `MIN_YEAR` re-export pattern, `format_fetch_error`).

## Scope

### In Scope (3 items, ~110 LoC, 1 PR)

- **B5** — `core/__init__.py:438` `DEFAULT_STATE["geometry"] = "720x600"` →
  `"850x600"`, aligning the persisted default with `app.py:227 minsize(850,600)`
  and the runtime fallback at `app.py:221`.
- **B6** — `app.py:513-531` `_on_close`: signal `self._cancel_event.set()` and
  `self.worker.join(timeout=2.0)` BEFORE `save_state`/`destroy`, so the worker's
  terminal `root.after(0, _update)` fires while the root is alive (token guard
  then discards the stale result) or the worker exits at its next checkpoint.
- **B7** — Re-export `MAX_RANGE_DAYS` from `core/__init__.py:39` (mirror the
  `MIN_YEAR` pattern from Change A), import it in `app.py:40-55`, and use it in
  `_validate_inputs` at `app.py:648-649` (comparison + f-string) instead of the
  hardcoded `730` literal.

### Out of Scope

- **Change A** `fix-data-layer-bugs`: B1-B4, B8-B9, Q4, Q5 (archived).
- **Change D**: items D1-D5 (deferred).
- **Change E**: items P1-P4 (deferred).
- **Change F**: items G1-G10 (deferred).
- **Change G**: items Q1, Q2, Q7, Q8 (deferred).

## Capabilities

### New Capabilities
None.

### Modified Capabilities

- `app-startup-and-imports` — ADDED requirement: `DEFAULT_STATE["geometry"]`
  SHALL equal the `minsize` floor (`850x600`) so first launch matches the
  runtime fallback and the persisted `state.json` is not stale.
- `gui-worker-lifecycle` — ADDED requirement: `_on_close` SHALL signal
  cooperative cancel and join the in-flight worker with a bounded timeout
  BEFORE destroying the root, closing the post-`destroy` `root.after` race.
- `input-validation` — MODIFIED requirement "CLI and GUI use the shared
  validators": the GUI `_validate_inputs` range cap SHALL use the canonical
  `MAX_RANGE_DAYS` (re-exported from `core`), not a hardcoded literal.

## Approach

Single PR, RED-first. B5/B7 are mechanical (one literal; three edits). B6 is
the only behavior change: insert `set()` + `join(timeout=2.0)` at the top of
`_on_close`, before any state mutation, with a rationale comment. Order
matters — join BEFORE destroy so the worker's `root.after(0, _update)` runs
while the root is alive and is harmlessly discarded by the generation-token
guard (`app.py:782`). The worker is a daemon thread (`app.py:687`), so a
timed-out join never blocks process exit.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `core/__init__.py:39` | Modified | B7 add `MAX_RANGE_DAYS` to `from .validators import (...)` re-export |
| `core/__init__.py:438` | Modified | B5 `DEFAULT_STATE["geometry"]` → `"850x600"` |
| `app.py:40-55` | Modified | B7 add `MAX_RANGE_DAYS,` to `from core import (...)` |
| `app.py:513-531` | Modified | B6 cancel + `join(2.0)` before `save_state`/`destroy` + rationale comment |
| `app.py:648-649` | Modified | B7 replace `730` literal + f-string with `MAX_RANGE_DAYS` |
| `tests/test_core.py` | Modified | B5, B7 RED-first cases |
| `tests/test_app.py` | Modified | B6 (fake-worker harness), B7 RED-first cases |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| B6 test flakiness from a real worker thread | Med | Use a controllable fake worker (event-gated or stubbed `is_alive`/`join`); never spawn a real thread in the test |
| B6 join timeout value (2.0s) disputed | Low | Judgment call surfaced here: 1s too aggressive for slow networks, 3s hangs close too long. 2s is the documented choice; behavior equivalent at 1s/3s if a maintainer prefers |
| B7 re-export order changes import cosmetics | Low | `noqa: F401` already present; no runtime effect |
| B5 | Low | No test pins `"720x600"`; `test_app.py` already expects `"850x600"` |

## Rollback Plan

`git revert <sha>` of the single PR. No data migration, no schema change, no
on-disk format change. `state.json` and the SQLite cache remain bit-identical.
Test suite returns to pre-change green (57 passing).

## Dependencies

None new. Pytest harness already bootstrapped. Depends on Change A being
archived (the `MIN_YEAR` re-export pattern and `max_year()` are referenced but
not modified here).

## Strict TDD — RED-first test names

Per `config.yaml:45 apply.tdd: true`, each item writes its failing test FIRST.

- **B5** — `tests/test_core.py::test_default_state_geometry_is_850x600`
- **B6** — `tests/test_app.py::test_on_close_sets_cancel_event`;
  `test_on_close_joins_worker_before_destroy`;
  `test_on_close_destroy_still_happens_on_join_timeout`
- **B7** — `tests/test_core.py::test_max_range_days_reexported_from_core`;
  `tests/test_app.py::test_validate_inputs_uses_max_range_days`

## Review Budget

~110 LoC << `config.yaml:48 review_budget: 400`. Single PR. Chained PRs: No.

## Success Criteria

- [ ] `pytest -q` green (57 + 6 new tests).
- [ ] `grep -n '720x600' core/__init__.py` returns zero matches.
- [ ] `grep -n 'MAX_RANGE_DAYS' core/__init__.py` returns one match (re-export).
- [ ] `grep -n '> 730' app.py` returns zero matches.
- [ ] Closing the window during a fetch no longer raises `TclError` in the worker.
