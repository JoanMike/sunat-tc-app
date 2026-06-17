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

## Out of Scope

- Killing the worker thread mid-`requests.get`; the Python runtime
  does not allow it. The contract is to drop the result, not to
  interrupt the I/O.
- A "pause / resume" control; cancel is terminal.
- Persisting the cancel state across app restarts.
