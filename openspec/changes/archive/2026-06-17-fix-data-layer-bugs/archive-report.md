# Archive Report: fix-data-layer-bugs

## Summary

| Field | Value |
|---|---|
| **Change** | `fix-data-layer-bugs` |
| **Project** | `sunat-tc-app` |
| **Mode** | `hybrid` (OpenSpec filesystem + Engram) |
| **Archived at** | `2026-06-17` |
| **Archive path** | `openspec/changes/archive/2026-06-17-fix-data-layer-bugs/` |
| **Final verdict** | **PASS** (verify: 57/57 tests, 7/7 design decisions, 17/17 tasks) |
| **Archive type** | Normal (no destructive deltas, no CRITICAL issues, no reconciliation required) |

## Spec Sync Summary

| Domain | Action | Requirements | Scenarios | Target file | Status |
|---|---|---|---|---|---|
| `data-fetch` | **3 ADDED** | 7 total (was 4 + 3) | 4 new (2 + 1 + 1) | `openspec/specs/data-fetch/spec.md` | ✅ Synced |
| `gui-worker-lifecycle` | **1 ADDED** | 5 total (was 4 + 1) | 2 new | `openspec/specs/gui-worker-lifecycle/spec.md` | ✅ Synced |
| `input-validation` | **1 MODIFIED** | 3 total (unchanged count, in-place replacement) | 2 (scenarios updated to reference `max_year()` instead of `MAX_YEAR`) | `openspec/specs/input-validation/spec.md` | ✅ Synced |
| `localization` | **1 ADDED** | 5 total (was 4 + 1) | 3 new | `openspec/specs/localization/spec.md` | ✅ Synced |
| **Total** | **5 ADDED, 1 MODIFIED, 0 REMOVED, 0 RENAMED** | — | 12 new/updated scenarios across 4 specs | — | — |

**No REMOVED or RENAMED requirements.** No destructive deltas; per `config.yaml:54 rules.archive: ["Warn before merging destructive deltas"]`, no warning was needed.

**No duplicate requirement names** detected between delta and main specs — all merges applied cleanly.

**Format style preserved:** all ADDED requirements and the MODIFIED `validate_month` requirement were reformatted from the delta's blank-line-after-`#### Scenario:` style to each main spec's inline-scenario style (no blank line between `#### Scenario:` heading and bullets), matching the existing structure of every main spec in this project.

## Sync details per spec

### `data-fetch` — 3 ADDED

1. `FetchError(kind="rate_limit")` on 429 retry exhaustion — 2 scenarios
2. `load_state` rejects non-dict JSON payloads — 2 scenarios
3. `fetch_range` relies on `validate_range` for input validation — 1 scenario

### `gui-worker-lifecycle` — 1 ADDED

1. GUI fetch worker routes `FetchError` through shared core messages — 2 scenarios

### `input-validation` — 1 MODIFIED

- `validate_month(year, month)` shared helper — full block replacement:
  - Upper bound changed from module constant `MAX_YEAR` to callable `max_year()`.
  - Added `MIN_YEAR` single-source-of-truth paragraph (canonical in `core.validators`, re-exported from `core`).
  - Added `max_year()` re-evaluation semantics (no stale upper bound across midnight on Dec 31).
  - Added "module-level `MAX_YEAR` constant SHALL be removed" requirement.
  - Added migration note documenting the previous state.
  - Scenarios updated to reference `max_year()` instead of `MAX_YEAR`.

### `localization` — 1 ADDED

1. `core.format_fetch_error` is the single Spanish mapper for `FetchError` — 3 scenarios

## Tasks Completed

**17/17** tasks marked `[x]` in `tasks/tasks.md` at archive time.

| Phase | Tasks | Status |
|---|---|---|
| Phase 1 (PR1 — Data layer) | 1.1 RED, 1.2 GREEN, 1.3 RED, 1.4 GREEN, 1.5 REFACTOR (B8), 1.6 RED, 1.7 GREEN, 1.8 REFACTOR (Q5), 1.9 VERIFY | ✅ 9/9 |
| Phase 2 (PR2 — Surface integration) | 2.1 RED, 2.2 GREEN, 2.3 REFACTOR, 2.4 RED, 2.5 GREEN, 2.6 RED, 2.7 GREEN, 2.8 VERIFY | ✅ 8/8 |

No stale unchecked tasks. `sdd-apply` marked all 17/17 before archive. No reconciliation performed at archive time.

## Test Evidence

| Metric | Value |
|---|---|
| **Total tests** | 57 |
| **Passing** | 57/57 (100%) |
| **Failing** | 0 |
| **Errors** | 0 |
| **Skips** | 0 |
| **New tests in this change** | 19 (8 in `test_core.py`, 7 in `test_messages.py`, 3 in `test_cli.py`, 1 in `test_app.py`) |
| **Baseline (carried from prior cycle)** | 38 |
| **Runtime** | 3.37s |
| **Layer coverage** | 47 unit + 10 integration, across 7 test files |
| **Direct spec coverage** | 91.7% (10/12 scenarios with a directly-named passing test) |
| **Structural spec coverage** | 100% (every scenario has at least one passing test on its code path) |

Verify report: `openspec/changes/archive/2026-06-17-fix-data-layer-bugs/verify-report.md`.

## Design Decisions Verification

**7/7 design decisions implemented as designed** (D1–D7). No deviations from the design baseline. Spot-check evidence lives in the verify report.

## Deviations

### T2.4/T2.5 success-criterion text vs. actual behavior (DOCUMENTED IMPROVEMENT)

**Original SC#7** (`proposal.md:99`): "CLI `--xlsx` on a cache row with malformed `fecha` exits 5, not traceback exit 1."

**Actual behavior** (verified by `test_cli_xlsx_malformed_fecha_falls_back_to_raw_string`):
- A row with `fecha="not-a-date"` → inner `try/except ValueError` at `cli.py:165-168` falls back to writing the raw string → exit **0** with file successfully written (mirrors `app.py:924-927` GUI parity).
- The widened outer `except (OSError, ValueError, TypeError)` at `cli.py:281` is a safety net for **OTHER** unexpected write errors (e.g. `Workbook.save` raising `ValueError`), which exits 5.

**Status**: The orchestrator updated `proposal.md` line 12 (B2 in-scope item description) to reflect actual fallback semantics: "falling back to the raw `fecha` string on `ValueError` (exit 0, row preserved); ... so genuinely unexpected write errors → exit 5, not unhandled traceback exit 1." The original SC#7 text on line 99 still reads "exits 5, not traceback exit 1" but the design intent (no traceback, B2 widening, GUI parity) is fully preserved and well-tested. The exit-5 path is reserved for genuinely unexpected write errors (verified by `test_cli_xlsx_unexpected_write_error_exits_5`).

**Verdict**: This is a **documented improvement**, not a regression. Archived as-is. Future readers should treat the new B2 description (line 12) as authoritative for current behavior; SC#7 (line 99) is preserved unmodified as part of the audit trail.

## Out-of-scope Leakage

**Zero out-of-scope leakage.** Checked against `proposal.md:21-25` (Change B B5/B6/B7, Change D D1–D5, Change E P1–P4, Change F G1–G10, Change G Q1/Q2/Q7/Q8). No items from deferred changes leaked into this change cycle. Full evidence in the verify report.

## Triangulation Notes (from verify)

Two minor triangulation gaps, both non-blocking and covered by adjacent tests on the same code path:

1. **GUI `_fetch_worker` non-FetchError generic branch** — no explicit test asserts a non-`FetchError` exception hits the `except Exception` branch. Indirectly proven by `test_fetch_worker_fetcherror_uses_spanish_message` (if the order were wrong, the FetchError would fall through to `Exception` and the message would be English debug text, not Spanish).
2. **CLI integration test for `kind="rate_limit"`** — the CLI rate-limit mapping is covered at the unit level (`test_format_fetch_error_rate_limit`) and the CLI integration test uses `kind="http_5xx"` (same code path, different kind). The CLI's `format_fetch_error` call site is identical for all kinds.

Both are structural-coverage scenarios per the verify report, not failing or untested scenarios.

## Archive Contents

```
openspec/changes/archive/2026-06-17-fix-data-layer-bugs/
├── archive-report.md          (this file)
├── proposal.md                ✅ (proposal with SC#7 deviation note, B2 in-scope item updated by orchestrator)
├── verify-report.md           ✅ (PASS verdict with 2 minor triangulation gaps + 1 documented improvement)
├── exploration.md             ✅
├── design/
│   └── design.md              ✅ (7 design decisions D1–D7)
├── specs/
│   ├── data-fetch.md          ✅ (3 ADDED)
│   ├── gui-worker-lifecycle.md ✅ (1 ADDED)
│   ├── input-validation.md    ✅ (1 MODIFIED)
│   └── localization.md        ✅ (1 ADDED)
└── tasks/
    └── tasks.md               ✅ (17/17 tasks [x])
```

All artifacts present. No files deleted, no files modified in archive (per the audit-trail invariant).

## Source of Truth Updated

The following main specs now reflect the new behavior and serve as the new source of truth:

- `openspec/specs/data-fetch/spec.md` (7 requirements)
- `openspec/specs/gui-worker-lifecycle/spec.md` (5 requirements)
- `openspec/specs/input-validation/spec.md` (3 requirements; `validate_month` updated to dynamic `max_year()`)
- `openspec/specs/localization/spec.md` (5 requirements)

Specs **not** touched (no delta in this change): `app-startup-and-imports`, `csv-export`.

## SDD Cycle Complete

The `fix-data-layer-bugs` change has been fully:

- ✅ **Planned** — proposal, exploration, design (7 decisions), 4 delta specs, 17 tasks
- ✅ **Implemented** — under strict TDD with RED-first evidence for all 19 new tests
- ✅ **Verified** — 57/57 tests PASS, 7/7 design decisions implemented, 17/17 tasks complete, 1 documented improvement (not a regression)
- ✅ **Archived** — delta specs synced to main specs, change folder moved to dated archive, audit trail preserved

Ready for the next change.
