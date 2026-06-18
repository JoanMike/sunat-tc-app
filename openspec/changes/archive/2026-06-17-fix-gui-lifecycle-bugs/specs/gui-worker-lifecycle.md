# Delta for gui-worker-lifecycle

> Delta spec for `fix-gui-lifecycle-bugs`.
> Main spec: `openspec/specs/gui-worker-lifecycle/spec.md`.

## ADDED Requirements

### Requirement: `_on_close` signals cancel and joins the worker before destroying the root

`SunatTCApp._on_close` SHALL, before any state mutation or `root.destroy()`,
set the cooperative cancel flag (`self._cancel_event.set()`) and, when a
worker thread exists and is alive, call `self.worker.join(timeout=...)` with a
bounded timeout. The join SHALL precede `save_state` and `self.root.destroy()`
so the worker's terminal `root.after(0, _update)` callback either fires while
the root is still alive (and is then harmlessly discarded by the generation-
token guard) or the worker exits at its next cancel check point. The join
timeout MUST be bounded (MUST NOT be unbounded) so a stalled socket cannot
hang the close; the worker is a daemon thread, so a timed-out join MUST NOT
block process exit.

#### Scenario: Close during an in-flight fetch

- GIVEN a worker thread is alive and a fetch is in progress
- WHEN the user closes the window (`_on_close` runs)
- THEN `_cancel_event` is set, the worker is joined (bounded timeout) BEFORE
  `root.destroy()`, the worker observes cancel and exits at its next check
  point, no `TclError` is raised in the worker thread, and state is still
  persisted

#### Scenario: Worker stuck on a slow network — join times out

- GIVEN a worker thread is alive but blocked past the join timeout
- WHEN `_on_close` runs
- THEN `join` returns after the bounded timeout without raising, `save_state`
  and `root.destroy()` still execute, and the close completes without hanging
  (the daemon worker does not block process exit)

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

## RENAMED Requirements

None.
