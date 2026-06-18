# Tasks: fix-gui-lifecycle-bugs

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~110 (prod ~15 + tests ~95) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-always |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | B5+B6+B7 together | PR 1 | base: main; ~110 LoC << 400 budget; single PR, one commit per RED+GREEN pair |

## Phase 1: B5 — Stale default geometry

- [x] 1.1 RED: add `tests/test_core.py::test_default_state_geometry_is_850x600` asserting `core.DEFAULT_STATE["geometry"] == "850x600"`; run `pytest -q` → RED
- [x] 1.2 GREEN: `core/__init__.py:438` change `"720x600"` → `"850x600"`; run `pytest -q` → GREEN
- [ ] 1.3 Commit (RED+GREEN pair)

## Phase 2: B6 — Cancel + join on close

- [x] 2.1 RED: add to `tests/test_app.py` a controllable fake-worker harness (stub `is_alive`/`join`, or event-gated) and three tests: `test_on_close_sets_cancel_event` (stub worker alive, call `_on_close`, assert `_cancel_event.is_set()`); `test_on_close_joins_worker_before_destroy` (event-gated fake worker, assert `join` called before `destroy`); `test_on_close_destroy_still_happens_on_join_timeout` (fake worker whose `join` "times out" — `is_alive()` stays True after join — assert `destroy` still called); run `pytest -q` → RED
- [x] 2.2 GREEN: `app.py:513-531` insert `self._cancel_event.set()` + `if self.worker and self.worker.is_alive(): self.worker.join(timeout=2.0)` at the top of `_on_close`, before state mutation, with the rationale comment from design D2; run `pytest -q` → GREEN
- [ ] 2.3 Commit (RED+GREEN pair)

## Phase 3: B7 — `MAX_RANGE_DAYS` re-export and use

- [x] 3.1 RED: add `tests/test_core.py::test_max_range_days_reexported_from_core` (`assert core.MAX_RANGE_DAYS == 730`); add `tests/test_app.py::test_validate_inputs_uses_max_range_days` (monkeypatch `core.MAX_RANGE_DAYS` to a small value, build a span exceeding it, assert `_validate_inputs` returns a message that interpolates the same value); run `pytest -q` → RED
- [x] 3.2 GREEN: `core/__init__.py:39` add `MAX_RANGE_DAYS` to the `from .validators import (...)` re-export (keep `# noqa: F401`); `app.py:40-55` add `MAX_RANGE_DAYS,` to the `from core import (...)` block; `app.py:648-649` replace `> 730` with `> MAX_RANGE_DAYS` and the literal message with `f"El rango máximo es de 2 años ({MAX_RANGE_DAYS} días)."`; run `pytest -q` → GREEN
- [ ] 3.3 Commit (RED+GREEN pair)

## Phase 4: Verify

- [x] 4.1 Run `.\venv\Scripts\python.exe -m pytest -q` → all green (57 + 6 new)
- [x] 4.2 `grep -n '720x600' core/__init__.py` → zero matches
- [x] 4.3 `grep -n '> 730' app.py` → zero matches
- [x] 4.4 `grep -n 'MAX_RANGE_DAYS' core/__init__.py` → one match (re-export)

> Note: commit tasks T1.3 / T2.3 / T3.3 ("Commit RED+GREEN pair") are
> intentionally SKIPPED per the hard user constraint "NO git operations".
> Working-tree edits + pytest only.
