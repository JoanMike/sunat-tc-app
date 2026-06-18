# GUI Worker Lifecycle Specification

## Purpose

Defines the GUI's contract for background fetch workers: how the user
can cancel a running query, how stale callbacks from a cancelled or
superseded worker are dropped, and how the status bar communicates
success vs. empty result vs. error. References: Engram `#1879`
(findings #1, #4, #12, #14), Engram `#1882` (Theme D, cross-cutting
concern #3), cached product decision 2A.

## Requirements

### Requirement: Dead `_cancelled` field removed

The `self._cancelled` attribute on `SunatTCApp` SHALL be removed; it
is written but never read. No other field, signal, or visible behavior
SHALL be lost in the removal.

#### Scenario: No references survive
- GIVEN the GUI source after the change
- WHEN `grep -n '_cancelled' app.py` is run
- THEN zero matches are returned

### Requirement: Explicit "Cancelar" button while a worker is running

`SunatTCApp` SHALL expose a "Cancelar" button that is visible and
enabled only while a worker thread is alive. Clicking the button
SHALL set a `threading.Event` (or equivalent cancel flag) that the
worker checks between HTTP attempts. The cancel action is opt-in: a
new quick-filter click does NOT auto-cancel a running query
(product decision 2A).

#### Scenario: Cancel button visible during fetch
- GIVEN a worker thread is alive
- WHEN the GUI is rendered
- THEN the "Cancelar" button is visible and enabled

#### Scenario: Click cancels the worker
- GIVEN a worker is running
- WHEN the user clicks "Cancelar"
- THEN the cancel flag is set, the worker terminates at the next
  safe check point, and the status bar shows a Spanish
  "Consulta cancelada." message

#### Scenario: Quick-filter during a running worker
- GIVEN a worker is running
- WHEN the user clicks a quick-filter button
- THEN the running query is not silently dropped; the GUI either
  shows a Spanish "Espere a que termine la consulta." message OR
  increments the generation token to start a new query. The chosen
  behavior is decided at design time, but the running worker MUST
  NOT no-op

### Requirement: Generation token discards stale `on_done` callbacks

`SunatTCApp` SHALL maintain a monotonic `self._worker_token`
(integer). Every new fetch increments it before the worker starts.
The `_update` closure scheduled by `_on_fetch_done` SHALL compare
its captured token against the current `self._worker_token` at the
top of `_update`; if they differ, the callback is silently discarded
without touching the table, the status bar, or the count label.

#### Scenario: Stale callback from a cancelled worker
- GIVEN worker A captured token `5` and is mid-flight
- WHEN the user cancels A and starts worker B, which captures token
  `6`
- AND worker A's `_on_fetch_done` later fires
- THEN `_update` sees `5 != 6` and discards the stale result

### Requirement: Status bar color reflects outcome kind

The status bar SHALL use at least three distinct colors: an info/busy
color while a worker is in flight, a success color when rows were
obtained, and a neutral (or info) color for "No se encontraron
datos…". The "Sin datos" path SHALL NOT use the success color.

#### Scenario: Empty result is not painted green
- GIVEN a query that returns no rows
- WHEN `_on_fetch_done` runs
- THEN the status text is "No se encontraron datos…" in a neutral
  or info color, not in the success green

#### Scenario: Successful result uses the success color
- GIVEN a query that returns N rows
- WHEN `_on_fetch_done` runs
- THEN the status text is in the success color

### Requirement: GUI fetch worker routes `FetchError` through shared core messages

`SunatTCApp._fetch_worker` SHALL catch `FetchError` BEFORE the generic
`except Exception` and call `core.format_fetch_error(exc)` to produce the
status-bar message passed to `on_done`. The GUI SHALL NOT fall back to
`str(exc)` (English-y technical text such as `"HTTP 503"`) for `FetchError`
exceptions — Spanish GUI users MUST see the mapped Spanish message from
`core.messages`. The generic `except Exception` branch is kept as a
safety net for non-`FetchError` exceptions and continues to use its
current `"Error inesperado: {exc}"` text.

#### Scenario: `FetchError` produces a Spanish status message
- GIVEN the worker raises `FetchError(kind="http_5xx")`
- WHEN `_on_fetch_done` runs
- THEN `on_done([], core.format_fetch_error(exc))` is called
- AND the status bar shows the mapped Spanish message
- AND `str(exc)` is NOT used as the user-visible text

#### Scenario: non-`FetchError` still uses the generic fallback
- GIVEN the worker raises an exception that is NOT a `FetchError`
  (e.g. `KeyError`, `RuntimeError`)
- WHEN `_on_fetch_done` runs
- THEN the generic `except Exception` branch handles it
- AND the `FetchError` branch does not match

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

### Requirement: Determinate progressbar for range mode

`SunatTCApp` SHALL present a determinate progressbar while a range fetch is
in flight, and an indeterminate progressbar for `today`/`month` fetches
(single network call, unknown duration).

The `progress_queue` items SHALL be a `ProgressUpdate(msg, value, maximum)`
namedtuple (previously a bare `str`). The worker thread SHALL construct
`ProgressUpdate` payloads but MUST NOT call any method on `self.progress`
directly — the progressbar value crosses the thread/Tk boundary only through
`progress_queue`, and only the main-thread `_poll_progress` (scheduled via
`root.after`) writes `self.progress["value"]`. For `range` fetches the worker
SHALL compute `total_months = (end.year - start.year)*12 +
(end.month - start.month) + 1` (mirroring `core.fetch_range`'s internal
formula) and emit `value = min(month_idx, total_months)`, `maximum =
total_months`. For `today`/`month` fetches the worker SHALL emit
`value = None`, `maximum = None`.

`_on_fetch` SHALL configure the bar per `params["kind"]` before the worker
starts: `range` → `mode="determinate"`, `maximum=total_months`, `value=0`;
`today`/`month` → `mode="indeterminate"`. `_poll_progress` SHALL set the
status text from `upd.msg` and, when `upd.value is not None`, set
`self.progress["value"] = upd.value`; when `upd.maximum is not None`, set
`self.progress["maximum"] = upd.maximum`. `_set_busy(True)` SHALL call
`self.progress.start(12)` only when `cget("mode") == "indeterminate"` (the
determinate bar is driven by fed values, not auto-bounce). `_set_busy(False)`
SHALL reset `self.progress["value"] = 0` so a previous range's full bar does
not linger.

The `total_months` formula duplicates `core.fetch_range`'s internal month
count; the duplication MUST be flagged with a comment so a future core change
updates both sites.

#### Scenario: Range mode configures a determinate bar

- GIVEN the user selects "Rango" mode with `start` and `end` spanning
  `total_months` months
- WHEN `_on_fetch` is invoked for a `range` fetch
- THEN `self.progress.cget("mode") == "determinate"`
- AND `self.progress.cget("maximum") == total_months`
- AND `self.progress["value"] == 0`

#### Scenario: Today/month mode configures an indeterminate bar

- GIVEN the user selects "Hoy" (or "Mes") mode
- WHEN `_on_fetch` is invoked for a `today` (or `month`) fetch
- THEN `self.progress.cget("mode") == "indeterminate"`

#### Scenario: Poll writes the fed value for a range fetch

- GIVEN the worker has pushed `ProgressUpdate(msg, value=2, maximum=5)` into
  `progress_queue` and the worker is still alive
- WHEN `_poll_progress` runs on the main thread
- THEN `self.status` text is set to `msg`
- AND `self.progress["value"] == 2`
- AND `self.progress["maximum"] == 5`

#### Scenario: Poll ignores value for an indeterminate fetch

- GIVEN the worker has pushed `ProgressUpdate(msg, value=None, maximum=None)`
  into `progress_queue`
- WHEN `_poll_progress` runs on the main thread
- THEN `self.status` text is set to `msg`
- AND `self.progress["value"]` is NOT changed by this poll

#### Scenario: Set-busy idle resets the value

- GIVEN a range fetch has completed and `self.progress["value"] == total_months`
- WHEN `_set_busy(False, ...)` is invoked
- THEN `self.progress["value"] == 0`
- AND `self.progress.stop()` has been called (safe no-op when not started)

## Out of Scope

- Killing the worker thread mid-`requests.get`; the Python runtime
  does not allow it. The contract is to drop the result, not to
  interrupt the I/O.
- A "pause / resume" control; cancel is terminal.
- Persisting the cancel state across app restarts.
