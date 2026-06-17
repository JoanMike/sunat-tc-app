# Exploration: Tighten queue-drain `except Exception:` to `except queue.Empty:` (mini-fix)

## Current State

`app.py` has two queue-drain loops that wrap `self.progress_queue.get_nowait()`
with a bare `except Exception: pass`. The standard library guarantees
`queue.Queue.get_nowait()` only raises `queue.Empty` on an empty queue, so the
broader catch is strictly over-catching and silently swallows unrelated bugs
(e.g. an `AttributeError` from a typo in a future refactor would be hidden
behind the drain loop).

### Affected Areas

- `app.py:701-706` — `SunatTCApp._poll_progress`, drains the progress queue
  while the worker is alive.
- `app.py:781-786` — `SunatTCApp._on_fetch_done._update` closure, drains any
  leftover progress messages so a late `_poll_progress` tick cannot paint a
  stale status.
- `app.py:27` — `import queue` (already present; `queue.Empty` is importable).
- `app.py:239` — `self.progress_queue: queue.Queue[str] = queue.Queue()`
  (type is `queue.Queue`; `get_nowait()` raises `queue.Empty` per stdlib docs).
- `tests/test_app.py` — no current test exercises the queue-drain path. The
  existing `_on_fetch_done` test (T3.2) covers stale-token drop, not the drain.

### Other `except Exception:` sites in `app.py` (broader audit, OUT OF SCOPE)

- `app.py:747` — `_fetch_worker` worker error handler. Catches
  `requests.RequestException`, `FetchError`, `ValueError`, anything from
  `fetch_day`/`fetch_month`/`fetch_range`. Marked `# noqa: BLE001` because the
  catch is intentionally broad (any worker failure must route to
  `on_done([], f"Error inesperado: {exc}")`).
- `app.py:946` — `_export_excel`. Catches any failure writing the XLSX and
  surfaces a Spanish `messagebox.showerror`. Marked `# noqa: BLE001` for the
  same reason: openpyxl + filesystem + file association failures are all
  possible and all must funnel to the same user-facing error path.

Both OUT OF SCOPE sites are deliberate broad catches with documented intent;
narrowing them to a single exception class would be a behavior change.

### Spec context (relevant authority)

`openspec/specs/app-startup-and-imports/spec.md:49` already states:
> "The bare `except Exception: pass` pattern SHALL NOT be used."

The two queue-drain sites are literal instances of that exact forbidden
pattern. The mini-fix brings the code into compliance with an EXISTING spec
requirement that PR 3 deferred. This is a stronger motivation than generic
"stdlib best practice" — it is spec compliance.

### Tests

- `tests/test_app.py` — 11 tests, none touch `progress_queue`/`get_nowait`/
  `queue.Empty`. Safe to add a new RED test (TDD-first per `strict_tdd: true`).
- Suggested RED test (for sdd-tasks): construct `SunatTCApp`, monkeypatch
  `self.progress_queue.get_nowait` to raise `RuntimeError("boom")`, then
  invoke `_poll_progress` (or `_on_fetch_done` then trigger `_update`) and
  assert the `RuntimeError` propagates instead of being swallowed.

## Approaches

1. **Narrow to `except queue.Empty:`** (recommended)
   - Pros: stdlib-idiomatic, brings code into compliance with the
     `app-startup-and-imports` spec rule, makes unrelated bugs observable.
   - Cons: 1-line change per site (2 lines total); requires a 2-line RED test
     if `strict_tdd` is honored.
   - Effort: Trivial (1 commit, 2 source lines + ~10 lines of test).

2. **Leave as `except Exception:` and add a `# noqa: BLE001` comment**
   - Pros: zero behavior change, no test churn.
   - Cons: actively conflicts with `app-startup-and-imports/spec.md:49`; the
     comment is exactly the marker the prior verify-report's SUGGESTION
     wanted to avoid.
   - Effort: Trivial but defeats the purpose of the mini-fix.

## Recommendation

Approach 1. The narrow catch is the only option that:
- Honors the existing spec rule.
- Surfaces real bugs (queue-drain path should never raise anything else).
- Matches stdlib best practice the user requested.
- Stays scoped to the flagged two lines (no behavior change elsewhere).

## Risks

- **Risk 1 (very low)**: a future change introduces a new exception in the
  drain loop. Mitigated by the project already requiring tests for
  behavior-changing edits; a regression test that asserts `RuntimeError`
  propagates would catch this.
- **Risk 2 (very low)**: `queue.Empty` is the only documented exception for
  `Queue.get_nowait()`. If a future Python release adds a new one (e.g.
  `TimeoutError`), the narrow catch would re-broaden. Probability: effectively
  zero — the stdlib `queue` module's contract has been stable for ~20 years.

## Ready for Proposal

Yes. The intent, scope, and approach are unambiguous; no clarifying questions
needed for the user. The sdd-propose phase can write a tight, scoped
proposal.md immediately.
