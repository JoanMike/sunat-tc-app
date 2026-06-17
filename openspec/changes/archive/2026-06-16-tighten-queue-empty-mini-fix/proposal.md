# Proposal: Tighten queue-drain `except Exception:` to `except queue.Empty:`

## Intent

Narrow two over-broad exception catches in the GUI's progress-queue drain
paths. `queue.Queue.get_nowait()` only raises `queue.Empty`, so the current
`except Exception: pass` blocks silently swallow unrelated bugs. Also
brings the code into compliance with the existing
`app-startup-and-imports/spec.md:49` rule that the bare `except Exception:
pass` pattern SHALL NOT be used.

## Scope

### In Scope

- Replace `except Exception:` with `except queue.Empty:` in
  `SunatTCApp._poll_progress` (wraps `progress_queue.get_nowait()`).
- Same in the `_update` closure inside `SunatTCApp._on_fetch_done` (wraps
  `progress_queue.get_nowait()`).
- Add a TDD RED test asserting a non-`Empty` exception from `get_nowait`
  propagates (per `strict_tdd: true`).

### Out of Scope

- The two other `except Exception:` blocks in `app.py` (`:747` `_fetch_worker`
  and `:946` `_export_excel`, both `# noqa: BLE001`) — deliberately broad
  for user-facing error routing; narrowing changes behavior.
- Any change to `cli.py`, `core.py`, or `tests/test_cli.py`.
- Any spec delta (behavior-preserving code-hygiene fix).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. `get_nowait` only raises `Empty`; the narrowed catch is
behaviorally identical to the old one.

## Approach

Pure stdlib exception narrowing. No control-flow change. `queue.Empty` is
already importable via `app.py:27`. The two `# noqa: BLE001`-marked broad
catches stay broad on purpose.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app.py:705` | Modified | `_poll_progress`: `except Exception:` → `except queue.Empty:` |
| `app.py:785` | Modified | `_on_fetch_done._update`: same replacement |
| `tests/test_app.py` | Modified | +1 RED test (non-`Empty` from `get_nowait` must propagate) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Spec compliance regression (someone reverts) | Low | RED test pins the contract |
| New `queue` exception added in a future Python release | Negligible | stdlib `queue` contract stable for ~20 years |
| Visible behavior change to user | None | `Empty` is the only thing `get_nowait` can raise |

## Rollback Plan

Single commit. `git revert` (user-side). No follow-up needed: no
spec/design/task artifact references the narrowed class name.

## Dependencies

None. `queue` is already imported at `app.py:27`. Pytest harness was
bootstrapped in PR 1 of the prior `fix/judgment-day-round-1` cycle.

## Success Criteria

- [ ] `grep -n 'except Exception' app.py` returns exactly 2 matches
  (lines 747 and 946, both `# noqa: BLE001`).
- [ ] `pytest -q` is green (existing 20 + 1 new test).
- [ ] Both queue-drain sites in `app.py` use `except queue.Empty:`.
- [ ] No new UI strings, no new Spanish copy, no new files outside
  `app.py` and `tests/test_app.py`.

## Change shape

- **Type**: code-hygiene / spec compliance. **Strict TDD**: true (1 RED
  test). **Budget**: 400 lines — change is ~12 LoC total; single PR, no
  chained split.
