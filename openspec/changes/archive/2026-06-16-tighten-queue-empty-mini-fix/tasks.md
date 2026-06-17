# Tasks: Tighten queue-drain `except Exception:` to `except queue.Empty:`

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~12 LoC (1 test ~7 LoC + 2 line replacements in `app.py`) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

> `size-exception` here is the closest valid label meaning "single PR, no chained
> split." The change is naturally well under the 400-line budget; no exception
> from a maintainer is being requested. The proposal already documents
> "single PR, no chained split."

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | RED test + narrow two catches + verify `pytest -q` green | PR 1 | All in one commit. ~12 LoC. Tests + code travel together. |

## Phase 1: RED — pin the contract with a failing test

- [x] 1.1 In `tests/test_app.py`, add `test_poll_progress_propagates_non_empty_exception` that monkeypatches `app.progress_queue.get_nowait` to raise `RuntimeError("simulated non-Empty failure")`, stubs `app.root.after` to a no-op so the reschedule does not keep the test alive, fakes an alive worker, and asserts `pytest.raises(RuntimeError, match="simulated non-Empty failure")`. Test lives in the file's existing T3.x section style; uses the `app` fixture + `monkeypatch`.
- [x] 1.2 Run `pytest -q tests/test_app.py::test_poll_progress_propagates_non_empty_exception` and confirm it FAILS — current `except Exception: pass` swallows `RuntimeError`. This is the RED step.

## Phase 2: GREEN — narrow the two queue-drain catches

- [x] 2.1 In `app.py` line 705 (`SunatTCApp._poll_progress`), replace `except Exception:` with `except queue.Empty:`. Keep the `pass` body. No import change: `queue` is already imported at `app.py:27`.
- [x] 2.2 In `app.py` line 785 (the `_update` closure inside `SunatTCApp._on_fetch_done`), same replacement. Keep the `pass` body.
- [x] 2.3 Run `pytest -q` and confirm the new test now passes AND the existing 20 tests remain green (21 total). This is the GREEN step.

## Phase 3: REFACTOR + verify success criteria

- [x] 3.1 Run `grep -n 'except Exception' app.py` and confirm exactly 2 matches remain: line 747 (`_fetch_worker`, `# noqa: BLE001`) and line 946 (`_export_excel`, `# noqa: BLE001`). Both are intentionally out of scope.
- [x] 3.2 Verify no new files, no new imports, no Spanish UI strings touched. Confirm diff stat: target ~12 LoC total (`tests/test_app.py` ~7 + `app.py` 2 line edits).

## Out of scope (do NOT do)

- Do NOT narrow `app.py:747` (`_fetch_worker`) or `app.py:946` (`_export_excel`) — both are deliberate `# noqa: BLE001` user-facing error routers; narrowing changes behavior.
- Do NOT touch `cli.py`, `core.py`, `tests/test_cli.py`, or any `openspec/specs/*.md`.
- Do NOT add a new dependency, new file, new Spanish copy, or new English comment beyond what the design specifies.
- Do NOT perform any git operations; user handles commit/PR manually.
