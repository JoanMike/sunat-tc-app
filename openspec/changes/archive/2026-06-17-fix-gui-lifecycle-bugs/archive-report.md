# Archive Report: fix-gui-lifecycle-bugs

## Summary

| Field | Value |
|---|---|
| **Change** | `fix-gui-lifecycle-bugs` |
| **Project** | `sunat-tc-app` |
| **Mode** | `hybrid` (OpenSpec filesystem + Engram) |
| **Archived at** | `2026-06-17` |
| **Archive path** | `openspec/changes/archive/2026-06-17-fix-gui-lifecycle-bugs/` |
| **Final verdict** | **PASS** (verify: 63/63 tests, 6/6 scenarios, 3/3 design decisions, 7/7 implementation tasks) |
| **Archive type** | Normal (no destructive deltas, no CRITICAL issues, no reconciliation required) |

## Spec Sync Summary

| Domain | Action | Requirements | Scenarios | Target file | Status |
|---|---|---|---|---|---|
| `app-startup-and-imports` | **1 ADDED** | 5 total (was 4 + 1) | 1 new | `openspec/specs/app-startup-and-imports/spec.md` | ✅ Synced |
| `gui-worker-lifecycle` | **1 ADDED** | 6 total (was 5 + 1) | 2 new | `openspec/specs/gui-worker-lifecycle/spec.md` | ✅ Synced |
| `input-validation` | **1 MODIFIED** | 3 total (unchanged count, in-place replacement) | 3 (2 retained + 1 new; retained "GUI rejects out-of-range year" updated to `max_year()`) | `openspec/specs/input-validation/spec.md` | ✅ Synced |
| **Total** | **2 ADDED, 1 MODIFIED, 0 REMOVED, 0 RENAMED** | — | 4 new/updated scenarios across 3 specs | — | — |

**No REMOVED or RENAMED requirements.** No destructive deltas; per `config.yaml rules.archive: ["Warn before merging destructive deltas"]`, no warning was needed.

**No duplicate requirement names** detected between delta and main specs — the 2 ADDED requirements are new; the MODIFIED "CLI and GUI use the shared validators" already existed and was replaced in place, not duplicated. All merges applied cleanly.

**Format style preserved:** all ADDED requirements and the MODIFIED requirement were reformatted from the delta's blank-line-after-`#### Scenario:` style to each main spec's inline-scenario style (no blank line between `#### Scenario:` heading and bullets), matching the existing structure of every main spec in this project. RFC 2119 keywords (`SHALL`, `MUST`, `MUST NOT`) and Given/When/Then formatting preserved verbatim.

## Sync details per spec

### `app-startup-and-imports` — 1 ADDED

1. `DEFAULT_STATE` geometry matches the `minsize` floor — 1 scenario
   - Fixes B5: stale `DEFAULT_STATE["geometry"] = "720x600"` literal that was clamped by `minsize(850, 600)` on first launch, persisting an inconsistent geometry to `state.json`.

### `gui-worker-lifecycle` — 1 ADDED

1. `_on_close` signals cancel and joins the worker before destroying the root — 2 scenarios
   - Fixes B6: close-without-cancel race that could raise a silent `TclError` in the worker thread. Ordering: `_cancel_event.set()` → bounded `worker.join(timeout=2.0)` → `save_state` → `root.destroy()`.

### `input-validation` — 1 MODIFIED

- `CLI and GUI use the shared validators` — full block replacement:
  - Added `MAX_RANGE_DAYS` single-source-of-truth paragraph (canonical in `core.validators`, re-exported from `core`; no duplicate definition in `core/__init__.py`).
  - Added requirement that the GUI `_validate_inputs` range-cap comparison and its Spanish error message SHALL use `MAX_RANGE_DAYS` (via the `core` re-export), not a hardcoded numeric literal.
  - Added migration note documenting the previous state (inlined literal `730` in both the comparison and the error f-string; `MAX_RANGE_DAYS` not re-exported from `core`).
  - Retained "CLI rejects future end-date" scenario (minor rewrap, semantics unchanged).
  - Updated "GUI rejects out-of-range year" scenario bound from `[MIN_YEAR, MAX_YEAR]` to `[MIN_YEAR, max_year()]` (consistent with the `validate_month` requirement already updated by Change A).
  - Added new scenario "GUI range cap uses the canonical `MAX_RANGE_DAYS`" — 1 new scenario.
  - Fixes B7: hardcoded `730` range cap in the GUI that could drift from `core.validators.MAX_RANGE_DAYS`.

## Tasks Completed

**7/7 implementation tasks** marked `[x]` in `tasks/tasks.md` at archive time.

| Phase | Tasks | Status |
|---|---|---|
| Phase 1 (B5 — Stale default geometry) | 1.1 RED, 1.2 GREEN | ✅ 2/2 |
| Phase 2 (B6 — Cancel + join on close) | 2.1 RED, 2.2 GREEN | ✅ 2/2 |
| Phase 3 (B7 — `MAX_RANGE_DAYS` re-export and use) | 3.1 RED, 3.2 GREEN | ✅ 2/2 |
| Phase 4 (Verify) | 4.1 pytest, 4.2 grep `720x600`, 4.3 grep `> 730`, 4.4 grep `MAX_RANGE_DAYS` | ✅ 4/4 |

### Stale-checkbox reconciliation note

The three commit tasks **T1.3 / T2.3 / T3.3** ("Commit RED+GREEN pair") remain `[ ]` in `tasks/tasks.md`. These are **NOT implementation tasks** — they are git-commit operations explicitly excluded by the hard user constraint **"NO git operations"** (the user handles git manually). The `tasks/tasks.md` footer documents this: *"commit tasks T1.3 / T2.3 / T3.3 are intentionally SKIPPED per the hard user constraint 'NO git operations'. Working-tree edits + pytest only."* The verify report independently confirms: *"The three commit tasks are intentionally `[ ]` per the hard user constraint 'NO git operations' — the user handles git manually. These are not implementation tasks and are not flagged."*

Per the sdd-archive Task Completion Gate, this is the orchestrator-approved exception: apply-progress and verify-report prove every implementation task is complete. The archived audit trail contains no stale unchecked **implementation** tasks. No mechanical reconciliation was performed (the checkboxes correctly reflect the no-git constraint, not incomplete work).

## Test Evidence

| Metric | Value |
|---|---|
| **Total tests** | 63 |
| **Passing** | 63/63 (100%) |
| **Failing** | 0 |
| **Errors** | 0 |
| **Skips** | 0 |
| **New tests in this change** | 6 (1 in `test_core.py` for `DEFAULT_STATE` geometry; 1 in `test_core.py` for `MAX_RANGE_DAYS` re-export; 3 in `test_app.py` for `_on_close` cancel/order/timeout; 1 in `test_app.py` for `_validate_inputs` using `MAX_RANGE_DAYS`) |
| **Baseline (carried from Change A)** | 57 |
| **Runtime** | 2.61s |
| **Strict TDD** | 4/4 spot-checks confirm RED-first (each new test would fail on pre-Change-B code) |
| **Direct spec coverage** | 6/6 scenarios COMPLIANT (100% direct) |

Verify report: `openspec/changes/archive/2026-06-17-fix-gui-lifecycle-bugs/verify-report.md`.

## Design Decisions Verification

**3/3 design decisions implemented as designed** (D1–D3). No deviations from the design baseline.

| Decision | Implemented as designed? | Note |
|---|---|---|
| D1 — B5: trivial literal change to `"850x600"` | **Yes** | `core/__init__.py:438`. Zero behavioral risk; aligns persisted default with `minsize` and runtime fallback. |
| D2 — B6: `set -> join(2.0) -> save_state -> destroy` with rationale comment | **Yes** | `app.py:516-528`. Comment documents the race, the token-guard discard, the 2.0s bound, and the daemon-thread safety net. Ordering verified by `test_on_close_joins_worker_before_destroy`. |
| D3 — B7: re-export via `core` mirroring `MIN_YEAR` pattern | **Yes** | `core/__init__.py:39` re-export; `app.py:43` imports from `core`. Single source in `validators.py:17`. Source-grep guard in `test_max_range_days_reexported_from_core` confirms no second definition. |

## Deviations

**None.** Implementation matches `design.md` exactly. Two judgment calls within the design's latitude (documented in the verify report, not regressions):

1. B6 rationale comment uses the design-D2 intent verbatim.
2. B7 test uses a 20-day span + monkeypatched cap=10 (stronger than the brief's 800-day example: a 20-day span is NOT rejected by the literal-`730` code, so only the constant-driven check can produce the error — proving both the comparison AND the message read `MAX_RANGE_DAYS`).

## Out-of-scope Leakage

**Zero out-of-scope leakage.** Working-tree changes touch ONLY B5/B6/B7. No items from deferred changes leaked in:

- No Change D items (README/AGENTS/config docs untouched).
- No Change E items (cache_put batching, sleep tuning untouched).
- No Change F items (GUI polish: today_label refresh, Ctrl+A, sort, Acerca de, progressbar determinate — untouched).
- No Change G items (ruff, `FetchError` kind validation, `__version__` untouched).

Grep confirms: `720x600` → 0 matches in the project; `> 730` literal in `app.py` → 0 matches; `MAX_RANGE_DAYS` defined once in `validators.py:17` and re-exported once in `core/__init__.py:39`.

## Archive Contents

```
openspec/changes/archive/2026-06-17-fix-gui-lifecycle-bugs/
├── archive-report.md          (this file)
├── proposal.md                ✅
├── verify-report.md           ✅ (PASS verdict, no deviations, no out-of-scope leakage)
├── exploration.md             ✅
├── design/
│   └── design.md              ✅ (3 design decisions D1–D3)
├── specs/
│   ├── app-startup-and-imports.md  ✅ (1 ADDED)
│   ├── gui-worker-lifecycle.md     ✅ (1 ADDED)
│   └── input-validation.md         ✅ (1 MODIFIED)
└── tasks/
    └── tasks.md               ✅ (7/7 implementation tasks [x]; 3 commit tasks [ ] per no-git constraint)
```

All artifacts present. No files deleted, no files modified in archive (per the audit-trail invariant).

## Source of Truth Updated

The following main specs now reflect the new behavior and serve as the new source of truth:

- `openspec/specs/app-startup-and-imports/spec.md` (5 requirements; added `DEFAULT_STATE` geometry floor)
- `openspec/specs/gui-worker-lifecycle/spec.md` (6 requirements; added `_on_close` cancel + join ordering)
- `openspec/specs/input-validation/spec.md` (3 requirements; "CLI and GUI use the shared validators" updated with `MAX_RANGE_DAYS` single-source-of-truth + new range-cap scenario)

Specs **not** touched (no delta in this change): `csv-export`, `data-fetch`, `localization` — these were synced in Change A (`fix-data-layer-bugs`) and have no Change B delta.

## SDD Cycle Complete

The `fix-gui-lifecycle-bugs` change has been fully:

- ✅ **Planned** — proposal, exploration, design (3 decisions), 3 delta specs, 10 tasks
- ✅ **Implemented** — under strict TDD with RED-first evidence for all 6 new tests (4/4 spot-checks)
- ✅ **Verified** — 63/63 tests PASS, 6/6 scenarios COMPLIANT, 3/3 design decisions implemented, 7/7 implementation tasks complete, no deviations, no out-of-scope leakage
- ✅ **Archived** — delta specs synced to main specs, change folder moved to dated archive, audit trail preserved, Engram archive observation recorded

Ready for the next change.
