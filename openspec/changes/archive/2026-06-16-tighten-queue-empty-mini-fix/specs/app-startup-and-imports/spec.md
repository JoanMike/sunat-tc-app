# Delta for app-startup-and-imports

> Delta spec for `tighten-queue-empty-mini-fix`.
> Main spec: `openspec/specs/app-startup-and-imports/spec.md`.

## ADDED Requirements

### Requirement: Narrow exception handling in queue-drain paths

The `_poll_progress` and `_on_fetch_done` queue-drain loops in `app.py`
MUST catch only `queue.Empty` from `progress_queue.get_nowait()`. Any
other exception raised inside the loop body MUST be allowed to propagate
so it can be observed and diagnosed rather than silently swallowed.

**Rationale.** `queue.Queue.get_nowait()` is contractually only allowed
to raise `queue.Empty`; a broader catch is a stdlib best-practice
violation that hides real bugs (a typo in a future refactor could
silently raise `AttributeError` and never be seen). The two queue-drain
sites are literal instances of the bare `except Exception: pass`
pattern already prohibited by the main spec's "`os.startfile` failures
are observable" requirement. This delta brings the code into compliance
with that existing rule and gives a stable home for the contract so it
does not drift again. The other two `except Exception:` sites in
`app.py` (`_fetch_worker` at `:747` and `_export_excel` at `:946`, both
`# noqa: BLE001`) are intentionally broad user-facing error routers and
remain out of scope.

#### Scenario: Empty queue exits the drain loop cleanly

- GIVEN a `_poll_progress` or `_on_fetch_done` drain loop over
  `progress_queue`
- WHEN `progress_queue.get_nowait()` raises `queue.Empty` (queue is empty)
- THEN the drain loop exits cleanly with no uncaught exception escaping

#### Scenario: Non-Empty exception in drain loop propagates

- GIVEN a `progress_queue.get_nowait()` call inside a `_poll_progress`
  or `_on_fetch_done` drain loop
- WHEN the call raises an exception other than `queue.Empty`
  (e.g. `RuntimeError`)
- THEN the exception propagates out of the loop (it is NOT silently
  swallowed)
