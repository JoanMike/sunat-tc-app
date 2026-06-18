# Archive Report: gui-polish-ux (Change F)

**Change**: gui-polish-ux
**Project**: sunat-tc-app
**Mode**: hybrid (openspec filesystem + Engram)
**Archived at**: 2026-06-17
**Final verdict**: PASS (verify: PASS WITH WARNINGS — no CRITICAL, archive-eligible)

## Summary

Change F (gui-polish-ux) — 5 GUI polish items in `app.py` + 9 RED-first tests
in `tests/test_app.py` — has completed the full SDD cycle: explore → propose
→ spec → design → tasks → apply → verify → archive. The change folder has
been moved to `openspec/changes/archive/2026-06-17-gui-polish-ux/` and the
two delta specs have been synced into the main specs (source of truth).

## Spec Sync Summary

| Domain | Action | Details |
|--------|--------|---------|
| `app-startup-and-imports` | Updated (appended) | 4 ADDED requirements: G1 `today_label` refreshes on entering "Hoy" mode, G2 `Ctrl+A` selects all tree rows, G3 Column sort on heading click with view-following export, G5 "Acerca de" dialog shows app version. No existing requirement modified or removed. |
| `gui-worker-lifecycle` | Updated (appended) | 1 ADDED requirement: G10 Determinate progressbar for range mode. No existing requirement modified or removed. |

**Duplicate-name check**: performed before sync. None of the 5 ADDED
requirement names collided with existing names in the main specs
(`app-startup-and-imports/spec.md` had 5 prior requirements, none matching;
`gui-worker-lifecycle/spec.md` had 6 prior requirements, none matching).
Post-sync verification: `app-startup-and-imports/spec.md` now has 9
`### Requirement:` headings (5 prior + 4 new); `gui-worker-lifecycle/spec.md`
now has 7 (6 prior + 1 new).

No other specs were touched.

## Task Completion

| Metric | Value |
|--------|-------|
| Tasks total | 11 |
| Tasks complete | 11 |
| Tasks incomplete | 0 |

All 11 task checkboxes in the archived `tasks/tasks.md` are `[x]`
(T1.1, T1.2, T2.1, T2.2, T3.1, T3.2, T4.1, T4.2, T5.1, T5.2, T6.1).
No stale unchecked implementation tasks. Task Completion Gate passed.

## Test Evidence

| Metric | Value |
|--------|-------|
| Test command | `.\venv\Scripts\python.exe -m pytest -q` |
| Baseline before F | 71 tests passing |
| After apply | 80 tests passing (71 existing + 9 new RED-first) |
| Final run | 80 passed / 0 failed / 0 skipped (14.29s) |
| New tests | 9 (G1×1, G2×1, G3×3, G5×1, G10×3) |

## Spec Compliance Matrix (from verify-report)

| Domain | Scenarios | ✅ COMPLIANT | ⚠️ PARTIAL | ❌ FAILING/UNTESTED |
|--------|-----------|--------------|------------|---------------------|
| app-startup-and-imports (G1/G2/G3/G5) | 9 | 8 | 1 (G3 export-follows, by construction) | 0 |
| gui-worker-lifecycle (G10) | 5 | 3 | 2 (G10 indeterminate-config, G10 poll-ignores-None, by construction) | 0 |
| **Total** | **14** | **11** | **3** | **0** |

Matrix coverage: 11/14 explicit (78.6%); 14/14 counting by-construction.
The 3 PARTIAL scenarios are SUGGESTION-level (implementation correct,
covered by construction; lack F-specific explicit assertion). No CRITICAL.

## Design Decisions (D1-D5)

All 5 design decisions implemented as designed. 3 documented deviations,
all IMPROVEMENTS (non-regressions):

1. **G10 `test_set_busy_resets_value_on_idle` strengthened** — asserts the
   full idle-reset contract (mode → "indeterminate" + value → 0) instead of
   value-only. Avoids a banned ghost-green trivial assertion (Tk's `stop()`
   already zeroes `["value"]` on this build). Implementation unchanged.
   **Judgement: improvement.**
2. **G3 heading base texts use the real labels** — `"Compra (S/)"` /
   `"Venta (S/)"` (not the design snippet's shorthand `"Compra"` /
   `"Venta"`), centralized in `_COLUMN_LABELS`. Prevents a `"(S/)"`
   suffix-loss regression on every sort indicator rewrite.
   **Judgement: improvement.**
3. **G3 helpers extracted** — `_rewrite_headings` and `_reset_sort_state`
   extracted as named helpers (design inlined the loops). Boy Scout dedup;
   two call sites share one helper. Behavior identical.
   **Judgement: improvement.**

**Deviation summary**: 3/3 improvements, 0/3 regressions. All surfaced in
the apply-progress artifact, none silent.

## CRITICAL Constraints

| Constraint | Status |
|------------|--------|
| G3 `tree.index(iid) → self.data[i]` invariant | ✅ Preserved — `_sort_by_column` sorts `self.data` in place + `_populate_table(self.data)` repopulates; `_get_rows_for_copy` unchanged. Verified by `test_sort_by_column_compra_ascending` (position-for-position). |
| G10 thread-safety (worker never touches `self.progress`) | ✅ Preserved — worker only `put`s `ProgressUpdate` into `progress_queue`; only main-thread `_poll_progress` writes `["value"]`/`["maximum"]`. Verified by `test_poll_progress_updates_value_for_range`. |

## Out-of-Scope Leakage

**None.** Change F touched ONLY `app.py` (production) and
`tests/test_app.py` (tests). No `core/`, no `cli.py`, no docs, no main
specs (until this archive sync), no Change G items. Other modified files
in `git status` are pre-existing uncommitted state from archived changes
A/B/C/D/E (per apply-progress Engram #1964).

## Archive Contents

- `exploration.md` ✅
- `proposal.md` ✅
- `specs/app-startup-and-imports/spec.md` ✅ (delta)
- `specs/gui-worker-lifecycle/spec.md` ✅ (delta)
- `design/design.md` ✅
- `tasks/tasks.md` ✅ (11/11 tasks complete)
- `verify-report.md` ✅

## Source of Truth Updated

The following main specs now reflect the new behavior:
- `openspec/specs/app-startup-and-imports/spec.md` (4 ADDED requirements)
- `openspec/specs/gui-worker-lifecycle/spec.md` (1 ADDED requirement)

## Engram Traceability

| Artifact | Topic Key | Obs ID |
|----------|-----------|--------|
| explore | `sdd/gui-polish-ux/explore` | (prior session) |
| proposal | `sdd/gui-polish-ux/proposal` | (prior session) |
| spec | `sdd/gui-polish-ux/spec` | (prior session) |
| design | `sdd/gui-polish-ux/design` | (prior session) |
| tasks | `sdd/gui-polish-ux/tasks` | (prior session) |
| apply-progress | `sdd/gui-polish-ux/apply-progress` | #1964 |
| verify | `sdd/gui-polish-ux/verify` | #1965 |
| archive-report | `sdd/gui-polish-ux/archive-report` | (saved this phase) |

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
Ready for the next change.
