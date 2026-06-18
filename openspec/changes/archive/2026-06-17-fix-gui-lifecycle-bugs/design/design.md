# Design: fix-gui-lifecycle-bugs

## Technical Approach

Three independent GUI-layer fixes, single PR, RED-first. B5 and B7 are
mechanical literal/import edits. B6 is the only behavior change: it inserts a
cooperative-cancel signal plus a bounded worker join at the top of `_on_close`,
before state persistence and root destruction, to close the race in which the
daemon worker calls `root.after(0, _update)` after `root.destroy()` and raises
a silent `TclError`. References:
- Spec: `openspec/changes/fix-gui-lifecycle-bugs/specs/{app-startup-and-imports,gui-worker-lifecycle,input-validation}.md`
- Exploration: `openspec/changes/fix-gui-lifecycle-bugs/exploration.md` (Engram #1932)

## Files (post-Change-A line numbers)

| File | Lines | Change |
| --- | --- | --- |
| `core/__init__.py` | `:39` | B7 add `MAX_RANGE_DAYS` to re-export |
| `core/__init__.py` | `:438` | B5 `"720x600"` → `"850x600"` |
| `app.py` | `:40-55` | B7 add `MAX_RANGE_DAYS,` to import block |
| `app.py` | `:513-531` | B6 insert cancel + join before save/destroy |
| `app.py` | `:648-649` | B7 replace `730` literal + f-string |
| `tests/test_core.py` | — | B5, B7 RED cases |
| `tests/test_app.py` | — | B6 (fake-worker harness), B7 RED cases |

## Architecture Decisions

### D1 — B5: trivial literal change

**Choice**: Set `DEFAULT_STATE["geometry"] = "850x600"`.
**Alternatives**: lower `minsize` to 720 (rejected — shrinks the UI below its
designed layout).
**Rationale**: The runtime fallback (`app.py:221`) and `minsize` (`:227`) are
already `850x600`; only the `DEFAULT_STATE` literal is stale. One line, zero
behavioral risk, aligns persisted default with runtime.

### D2 — B6: set → join(2.0) → save_state → destroy

**Choice**: At the top of `_on_close`, before any state mutation:
`self._cancel_event.set()`; then
`if self.worker and self.worker.is_alive(): self.worker.join(timeout=2.0)`;
then the existing `save_state(self.state)` + `self.root.destroy()`.
**Alternatives**: (a) set + destroy only, no join — leaves the race fully open
(rejected); (b) set + unbounded join — a hung socket hangs the close (rejected).
**Rationale**: Join BEFORE destroy so the worker's `root.after(0, _update)`
(`app.py:796`) fires while root is alive and is discarded by the token guard
(`app.py:782`); bounded 2.0s timeout so a stalled socket cannot hang the UI;
daemon thread (`app.py:687`) guarantees a timed-out join never blocks process
exit. Mirrors the liveness guard already in `_on_cancel`. A rationale comment
MUST accompany the code. The 2.0s value is a judgment call: 1s too aggressive
for slow networks, 3s hangs close too long.

### D3 — B7: re-export via `core`, mirror `MIN_YEAR`

**Choice**: `core/__init__.py:39` →
`from .validators import MAX_RANGE_DAYS, MIN_YEAR, validate_month, validate_range  # noqa: F401`;
add `MAX_RANGE_DAYS,` to `app.py` `from core import (...)`; use it in
`_validate_inputs` comparison and f-string.
**Alternatives**: import directly from `core.validators` in `app.py` (rejected
— breaks the established pattern; `app.py` imports `MIN_YEAR`, `validate_*`
from `core`, not from `core.validators`).
**Rationale**: Single source of truth in `validators.py`; matches the import
style Change A established for `MIN_YEAR`; `validate_range` and the GUI can
never drift. `noqa: F401` already covers the re-export.

## Before / After

### B5 — `core/__init__.py:437-444`
```python
# Before
DEFAULT_STATE: dict = {
    "geometry": "720x600",
    ...
}
# After
DEFAULT_STATE: dict = {
    "geometry": "850x600",
    ...
}
```

### B6 — `app.py:513-531`
```python
# Before
def _on_close(self) -> None:
    """Persiste geometría + modo + fechas antes de cerrar."""
    self.state["geometry"] = self.root.geometry()
    ...
    save_state(self.state)
    self.root.destroy()

# After
def _on_close(self) -> None:
    """Persiste geometría + modo + fechas antes de cerrar."""
    # Signal cooperative cancel and join the in-flight worker BEFORE destroying
    # the root. The worker's terminal on_done schedules root.after(0, _update)
    # from the worker thread; if destroy() runs first, root.after raises
    # TclError. Joining first lets the worker observe cancel at its next check
    # point and fire on_done while the root is alive, so the generation-token
    # guard harmlessly discards the stale result. Bounded 2.0s timeout so a
    # stalled socket cannot hang the close; the worker is a daemon thread, so a
    # timed-out join never blocks process exit.
    self._cancel_event.set()
    if self.worker and self.worker.is_alive():
        self.worker.join(timeout=2.0)
    self.state["geometry"] = self.root.geometry()
    ...
    save_state(self.state)
    self.root.destroy()
```

### B7 — `core/__init__.py:39` + `app.py:648-649`
```python
# Before (core/__init__.py:39)
from .validators import MIN_YEAR, validate_month, validate_range  # noqa: F401
# After
from .validators import MAX_RANGE_DAYS, MIN_YEAR, validate_month, validate_range  # noqa: F401

# Before (app.py:648-649)
if (ed - sd).days > 730:
    return False, "El rango máximo es de 2 años (730 días).", {}
# After
if (ed - sd).days > MAX_RANGE_DAYS:
    return False, f"El rango máximo es de 2 años ({MAX_RANGE_DAYS} días).", {}
```

## Testing Strategy

| Layer | What | Approach |
| --- | --- | --- |
| Unit (B5) | `core.DEFAULT_STATE["geometry"] == "850x600"` | `tests/test_core.py::test_default_state_geometry_is_850x600` |
| Unit (B6) | `_on_close` sets cancel, joins before destroy, destroy still happens on timeout | `tests/test_app.py` with a controllable fake worker (stub `is_alive`/`join`, or event-gated); never spawn a real thread |
| Unit (B7) | `MAX_RANGE_DAYS` re-exported; `_validate_inputs` uses it | `tests/test_core.py::test_max_range_days_reexported_from_core`; `tests/test_app.py::test_validate_inputs_uses_max_range_days` (monkeypatch `core.MAX_RANGE_DAYS` to a small value, assert message interpolates it) |

RED-first per `strict_tdd: true`: each test is written and run RED before the
matching GREEN edit. B6's fake-worker harness is the only non-trivial test
scaffold — it MUST stub `is_alive()`/`join()` (or block on an event the test
releases) so the assertion is deterministic and not timing-flaky.

## Migration / Rollout

No migration required. Rollback = `git revert <sha>` of the single PR. No
schema, cache, or on-disk format change.

## PR Split

Single PR, ~110 LoC, well under `review_budget: 400`.

## Open Questions

None. The B6 join timeout (2.0s) is a documented judgment call (see D2); it
does not block implementation and is equivalent at 1s/3s if a maintainer
prefers.
