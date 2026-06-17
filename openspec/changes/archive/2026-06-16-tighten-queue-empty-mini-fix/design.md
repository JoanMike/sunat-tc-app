# Design: Tighten queue-drain `except Exception:` to `except queue.Empty:`

## Technical Approach

Replace the two over-broad `except Exception: pass` blocks at the GUI
queue-drain sites with `except queue.Empty: pass`. The change is a
stdlib exception narrowing — no control-flow change, no new imports,
no new files. A single RED-first pytest test (per `openspec/config.yaml`
`strict_tdd: true`) pins the contract by asserting that a non-`Empty`
exception from `progress_queue.get_nowait()` propagates out of
`_poll_progress` instead of being silently swallowed.

The fix brings `app.py` into compliance with the existing
`app-startup-and-imports/spec.md` (Requirement "`os.startfile` failures
are observable", line 49): the bare `except Exception: pass` pattern
SHALL NOT be used. The two `# noqa: BLE001`-marked broad catches at
`app.py:747` and `:946` are deliberately out of scope (user-facing
error routing; narrowing changes behavior).

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Catch class | `queue.Empty` | Keep `Exception`; add `as exc`; log+reraise | `Queue.get_nowait` only raises `Empty` (stdlib contract stable ~20y). Narrowing surfaces future unrelated bugs at the same lines. |
| Import path | Reuse `queue` already imported at `app.py:27` | Add explicit `from queue import Empty` | Avoids churn; `queue.Empty` resolves from the existing module. The proposal explicitly says no new imports. |
| Out-of-scope broad catches (`:747`, `:946`) | Leave as `except Exception:  # noqa: BLE001` | Narrow them too | They are user-facing error routing (`on_done([], f"Error inesperado: {exc}")` and `messagebox.showerror` in the export path). Narrowing would change behavior. The `# noqa: BLE001` is a deliberate, documented choice. |
| Test target | `_poll_progress` only | Test both sites; or test only the closure | The two sites are structurally identical, so one test is sufficient. `_on_fetch_done._update` runs in a Tk `after(0, ...)` callback whose exceptions are swallowed by the Tcl event loop, so a clean RED assertion is unreliable there. The proposal's "1 RED test" budget matches this. |
| Test mock surface | `progress_queue.get_nowait` + `root.after` | Mock the whole queue | Minimal patch; preserves the queue type so `queue.Empty` resolution is exercised. `root.after` stubbed so the reschedule doesn't keep the test alive. |
| `tmp_cache_dir` fixture | Reuse existing `tests/conftest.py` fixture | Add new fixture | Already used by every test in `test_app.py` via the `app` fixture. |

## Data Flow

Unchanged. The drain pattern remains:

```
progress_queue.get_nowait()  →  on _Empty_:  pass  (legitimate "queue drained")
                            →  on anything else:  propagate  (bug, surfaces immediately)
```

Before: any exception is swallowed — unrelated bugs go unnoticed. After:
only `queue.Empty` is the silent exit; everything else surfaces to the
Tk event loop / caller.

## File Changes

| File | Action | Description |
|---|---|---|
| `app.py` | Modify (line 705) | In `_poll_progress`, change `except Exception:` to `except queue.Empty:`. The `pass` body is preserved. |
| `app.py` | Modify (line 785) | In `_on_fetch_done._update`, same replacement. The `pass` body is preserved. |
| `tests/test_app.py` | Modify | Add one RED test: `test_poll_progress_propagates_non_empty_exception`. Uses the existing `app` fixture and `monkeypatch`. |

No new files. No deletions. No changes to `cli.py`, `core.py`, or any
`openspec/specs/*.md` (behavior-preserving code-hygiene fix).

## Interfaces / Contracts

No new interfaces. The implicit contract becomes explicit by virtue of
the test:

> Both queue-drain sites in `app.py` SHALL catch only `queue.Empty`. Any
> other exception from `progress_queue.get_nowait()` SHALL propagate.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (RED) | Non-`Empty` exception from `get_nowait` propagates out of `_poll_progress` | `monkeypatch.setattr(app.progress_queue, "get_nowait", boom)` where `boom` raises `RuntimeError("simulated non-Empty failure")`; stub `app.root.after` to a no-op; fake an alive worker; assert `pytest.raises(RuntimeError, match="simulated non-Empty failure")`. |
| Regression | Existing 20 tests remain green | `pytest -q` after the fix. |
| Manual / E2E | None | Scope is too small; a code-hygiene fix doesn't introduce new GUI behavior. |

The RED test will fail against the current `app.py` (the `except
Exception: pass` swallows `RuntimeError`), and pass against the fixed
code.

## Migration / Rollout

No migration required. Single-commit change, ~12 LoC total, no spec
delta, no user-facing behavior change. `git revert` is the rollback
(user-side; per the hard constraint, no git operations are performed
in this session).

## Open Questions

- [x] None. The proposal, the existing spec, and the localized code are
  sufficient to design the change without further input. The two
  queue-drain sites are symmetric; one test pins the contract for both.
