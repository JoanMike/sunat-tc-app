# Delta for gui-worker-lifecycle

> Change F (gui-polish-ux). One ADDED requirement covering G10 (determinate
> progressbar for range mode). No existing requirement in this spec is
> modified or removed.

## ADDED Requirements

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
