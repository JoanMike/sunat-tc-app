# Exploration: fix-gui-lifecycle-bugs (Change B)

> Scope: 3 items, ~110 LoC, single chained PR. Depends on Change A
> (`max_year()`, canonical `MIN_YEAR`, `core/messages.format_fetch_error`).
> Strict TDD is ON (`openspec/config.yaml`): implementation is RED-first.
> Artifact language: English. Read-only investigation — no production code touched.

## Current State

Three independent lifecycle bugs in the GUI layer, all small and localized:

- **B5 — stale default geometry.** `core/__init__.py:438` defines
  `DEFAULT_STATE["geometry"] = "720x600"`, but `app.py:227` calls
  `self.root.minsize(850, 600)`. On first launch Tk clamps the window to
  850×600; `state.json` lies with `"720x600"` until the user closes the
  window and `_on_close` persists the real geometry. The runtime fallback
  at `app.py:221` (`self.state.get("geometry", "850x600")`) is already
  correct — only the `DEFAULT_STATE` literal is stale.
- **B6 — `_on_close` leaves the worker thread alive.** `app.py:513-531`
  (`_on_close`) persists state then calls `self.root.destroy()` with no
  reference to the in-flight worker. A cooperative cancel mechanism
  exists (`self._cancel_event` at `app.py:240`, used by `_on_cancel` at
  `app.py:624-631`) but `_on_close` never signals it. If the user closes
  the window mid-fetch, the daemon worker keeps running and its terminal
  `_on_fetch_done` (`app.py:766-796`) calls `self.root.after(0, _update)`
  **from the worker thread** after `root.destroy()` → silent `TclError`
  in the worker thread, plus a possible late cache write during teardown.
- **B7 — magic number `730` in app.py.** `app.py:648-649` hardcodes
  `if (ed - sd).days > 730: ... "El rango máximo es de 2 años (730 días)."`.
  The canonical constant `MAX_RANGE_DAYS = 730` lives at
  `core/validators.py:17` and is already used by `validate_range`
  (`core/validators.py:30-31`). `core/__init__.py:39` re-exports
  `MIN_YEAR, validate_month, validate_range` but **not** `MAX_RANGE_DAYS`,
  so app.py cannot import it today without touching the re-export line.

## Affected Areas

- `core/__init__.py:438` — `DEFAULT_STATE["geometry"]` literal (B5).
- `core/__init__.py:39` — `from .validators import (...)` re-export line; add
  `MAX_RANGE_DAYS` to mirror the `MIN_YEAR` re-export Change A established (B7).
- `app.py:40-55` — `from core import (...)` block; add `MAX_RANGE_DAYS` next to
  `MIN_YEAR` for import-style consistency (B7).
- `app.py:648-649` — replace the `730` literal and the f-string with
  `MAX_RANGE_DAYS` (B7).
- `app.py:513-531` — `_on_close`: insert cancel-signal + bounded join before
  `save_state`/`destroy` (B6).
- `tests/test_app.py` — new RED tests for `_on_close` worker teardown (B6); B5/B7
  covered by extending existing default-state / validation-message assertions.

## Approaches

### B5 — default geometry
1. **Set `DEFAULT_STATE["geometry"] = "850x600"`** — single literal edit.
   - Pros: zero behavioral risk; aligns the persisted default with `minsize`
     and with the runtime fallback at `app.py:221`; the existing
     `test_geometry_tclerror_falls_back` already asserts `"850x600"`.
   - Cons: none.
   - Effort: Low (1 line).
2. *No real alternative* — the value must equal `minsize` width (850) to be
   self-consistent. Rejected: lowering `minsize` to 720 would shrink the UI
   below its designed layout.

### B6 — cancel + join on close (design choice: ordering & timeout)
1. **set → join(2.0) → save_state → destroy** (recommended).
   - Insert at the **top** of `_on_close`, before any state mutation:
     `self._cancel_event.set()`; then
     `if self.worker and self.worker.is_alive(): self.worker.join(timeout=2.0)`;
     then the existing `save_state(self.state)` + `self.root.destroy()`.
   - Why join **before** destroy: the worker's terminal
     `on_done` → `self.root.after(0, _update)` runs **in the worker thread**
     (`app.py:796`). If `destroy()` runs first, `root.after` raises
     `TclError` in the worker. Joining first lets the worker observe the
     cancel at its next checkpoint (`app.py:728/733/758`) and call `on_done`
     **while root is still alive**, so `root.after` succeeds and `_update`'s
     token guard (`captured_token != self._worker_token`, `app.py:782`)
     harmlessly discards the stale result.
   - Why a **bounded** 2.0s timeout: the worker may be blocked in a single
     network call (`fetch_day`/`fetch_month` are atomic; `fetch_range`
     checks cancel only between per-day fetches via the `progress` callback).
     A join with no timeout could hang the UI on a stalled socket. 2s is
     long enough for a cooperative exit, short enough to feel responsive.
   - Why safe even on timeout: the worker is a **daemon** thread
     (`app.py:687`), so a timed-out join does **not** block process exit —
     it only narrows the window in which a post-`destroy` `root.after` could
     fire.
   - Pros: closes the `TclError`-in-worker race; bounded; no new state.
   - Cons: 2s worst-case wait on close during a stuck fetch (acceptable, and
     only on the stuck path).
   - Effort: Low–Med (~6 LoC + 1 rationale comment).
2. **set → destroy only (no join).** Signal cancel and tear down immediately.
   - Pros: no wait on close.
   - Cons: leaves the race fully open — the worker can still call
     `root.after` after `destroy`. Rejects the whole point of B6.
3. **set → join with no timeout.**
   - Pros: strongest guarantee.
   - Cons: a hung socket hangs the close → bad UX. Rejected.

### B7 — use `MAX_RANGE_DAYS` from core
1. **Re-export from `core` + import in app.py (mirror `MIN_YEAR`)** (recommended).
   - `core/__init__.py:39` →
     `from .validators import MAX_RANGE_DAYS, MIN_YEAR, validate_month, validate_range`.
   - `app.py:40-55` → add `MAX_RANGE_DAYS,` to the `from core import (...)`
     block alongside `MIN_YEAR`.
   - `app.py:648-649` →
     `if (ed - sd).days > MAX_RANGE_DAYS:` and
     `f"El rango máximo es de 2 años ({MAX_RANGE_DAYS} días)."`.
   - Pros: single source of truth in `validators.py`; matches the import
     style Change A established for `MIN_YEAR`; `validate_range` and the GUI
     can never drift.
   - Cons: touches `core/__init__.py` re-export line (minimal, expected).
   - Effort: Low (3 edits).
2. **Import directly from `core.validators` in app.py** (no re-export).
   - Pros: zero churn in `core/__init__.py`.
   - Cons: breaks the established pattern — app.py imports `MIN_YEAR`,
     `validate_*` from `core`, not from `core.validators`. Inconsistent.
     Rejected for style consistency.

## Recommendation

- **B5**: Approach 1 — set `DEFAULT_STATE["geometry"] = "850x600"`.
- **B6**: Approach 1 — `set()` → `join(timeout=2.0)` → `save_state` →
  `destroy()`, with a comment explaining the daemon-thread + `root.after`
  race and why the timeout is bounded. Mirror the liveness guard already in
  `_on_cancel` (`self.worker and self.worker.is_alive()`).
- **B7**: Approach 1 — re-export `MAX_RANGE_DAYS` from `core` and use it in
  both the comparison and the f-string in `app.py`.

## Risks

- **B6 test determinism (highest).** `_on_close`'s join path only triggers
  when a worker is alive. A RED test needs a **controllable worker** (e.g. an
  event-gated fake `_fetch_worker` or a monkeypatched `threading.Thread`
  whose `is_alive()`/`join()` are stubbed) to assert (a) `_cancel_event`
  is set, (b) `worker.join` is called with a bounded timeout, (c) ordering
  is set→join→save→destroy. Without a fake worker the test would be
  timing-flaky. This is a **spec/apply design constraint**, not a blocker.
- **B6 timeout value.** 2.0s is a judgment call; if maintainers prefer 1s
  or 3s the behavior is equivalent. Surface in the proposal for confirmation.
- **B7 re-export ordering.** Adding `MAX_RANGE_DAYS` to the re-export line is
  cosmetic-only (import order); no runtime effect. The `noqa: F401` already
  covers re-exports.
- **B5**: no risk — no test pins `"720x600"`; `test_core.py` compares against
  `dict(core.DEFAULT_STATE)` (whatever it is), and `test_app.py` already
  expects `"850x600"`.
- **Strict TDD**: all three must land RED-first. B5/B7 are straightforward
  assertion additions; B6 requires the fake-worker harness above.

## Ready for Proposal

**Yes.** All three items are verified, localized, and independently
testable. Line numbers confirmed (shifted +2 vs. the brief due to Change A
edits: `DEFAULT_STATE` now at `core/__init__.py:437-444`, `_on_close` at
`app.py:513-531`, the `730` check at `app.py:648-649`, `minsize` at
`app.py:227`). The orchestrator should tell the user:

1. Change B is ready to move to **propose**.
2. One open decision to confirm at propose/spec time: the **B6 join timeout
   (2.0s)** — acceptable, or prefer 1s/3s?
3. B6 will need a fake/controllable worker in tests (spec should call this
   out as a testability requirement).
