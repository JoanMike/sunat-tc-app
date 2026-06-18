# Archive Report: perf-cache-batching (Change E)

## Change

- **Name**: `perf-cache-batching` (Change E)
- **Project**: `sunat-tc-app`
- **Mode**: hybrid (openspec files + Engram)
- **Archived at**: 2026-06-17
- **Final verdict**: PASS

## Summary

Four performance fixes in `core/__init__.py` (P1-P4): batched cache writes
via `cache_put_many`, schema DDL only when the DB file is missing, single
cache read per month via `_fetch_month_with_flag`, and courtesy sleep reduced
from 0.3s to 0.1s. No behavior or API breakage; pure performance.

## Spec Sync Summary

| Domain | Action | Details |
|--------|--------|---------|
| `data-fetch` | Updated | 2 ADDED requirements + 1 MODIFIED requirement synced to `openspec/specs/data-fetch/spec.md` |

### Synced deltas

| # | Operation | Requirement | Target location |
|---|-----------|-------------|-----------------|
| 1 | ADDED | Batched cache writes via `cache_put_many` | `openspec/specs/data-fetch/spec.md` (appended to Requirements) |
| 2 | ADDED | Schema DDL runs only when the database file is missing | `openspec/specs/data-fetch/spec.md` (appended to Requirements) |
| 3 | MODIFIED | Cache-hit short-circuit in `fetch_range` | `openspec/specs/data-fetch/spec.md` (replaced existing block; new text covers single-read + 0.1s sleep) |

All other requirements in `data-fetch/spec.md` were preserved. No other
specs were touched (Change E had no delta for them).

## Tasks

- **Completed**: 7/7
- **Unchecked implementation tasks**: 0

| Task | Description | Status |
|------|-------------|--------|
| T1.1 | RED — P1 tests (`cache_put_many`, upsert, wrapper, `fetch_month` batch) | `[x]` |
| T1.2 | GREEN — P1 implementation (`cache_put_many`, `cache_put` wrapper, batch writes) | `[x]` |
| T2.1 | RED — P2 tests (DDL skip when DB exists, DDL run when DB missing) | `[x]` |
| T2.2 | GREEN — P2 implementation (`CACHE_DB.exists()` guard in `_connect`) | `[x]` |
| T3.1 | RED — P3+P4 tests (single cache read, 0.1s sleep; regression guard green) | `[x]` |
| T3.2 | GREEN — P3+P4 implementation (`_fetch_month_with_flag`, delete `_month_requires_network`, `sleep(0.1)`) | `[x]` |
| T4.1 | VERIFY — `pytest -q` green; regression guard; review budget | `[x]` |

## Test Evidence

- **Test command**: `.\venv\Scripts\python.exe -m pytest -q`
- **Result**: 71/71 PASSED (63 baseline + 8 new RED-first), 0 failed, 0 errors.
- **Critical regression**: `test_fetch_range_cache_hit_skips_sleep` — GREEN.
- **Spec matrix**: 8/8 scenarios covered by passing tests (100%).

## Design Decisions (D1-D4)

| Decision | Implemented | Note |
|----------|-------------|------|
| D1 — `cache_put_many` single impl + `cache_put` wrapper | Yes | Deviation: accepts 3-or-4 tuples (improvement; see below). |
| D2 — `CACHE_DB.exists()` guard before connect | Yes | Deviation: two connects on missing-file path (as-designed; see below). |
| D3 — `_fetch_month_with_flag` helper; drop `_month_requires_network` | Yes | As designed. |
| D4 — `time.sleep(0.1)` with justification comment | Yes | As designed. |

## Deviation Notes (2 documented, both improvements / non-regressions)

1. **D1 — `cache_put_many` accepts 3-or-4 tuples**: Implementation uses
   `r[3] if len(r) > 3 else source`, allowing `fetch_day`/`fetch_month` to
   pass 3-tuples without repeating the default source. The 4-tuple path
   (used by `cache_put` and the upsert test) works exactly as designed.
   **Judgment**: improvement — added flexibility, no behavioral regression.

2. **D2 — Two `sqlite3.connect` calls on the missing-file path**: An init
   connection runs DDL and closes, then a second connection is returned.
   This matches the D2 `After` block exactly. It is the logical consequence
   of the chosen approach: `sqlite3.connect` creates the file, so the
   `exists()` check must happen before any connect. The hot path
   (existing-file) uses exactly ONE connect with zero DDL. The cost is paid
   only once on the first-ever call. **Judgment**: as-designed,
   non-regression.

## Out-of-scope Leakage

None. Only `core/__init__.py` (production) and `tests/test_core.py` (tests)
were modified for Change E. No GUI, CLI, lint, or docs changes.

## Archive Contents

- `exploration.md`
- `proposal.md`
- `specs/data-fetch.md` (delta)
- `design/design.md`
- `tasks/tasks.md` (7/7 `[x]`)
- `verify-report.md`
- `archive-report.md` (this file)

## Source of Truth Updated

The following main spec now reflects the new behavior:
- `openspec/specs/data-fetch/spec.md` — 2 ADDED + 1 MODIFIED requirement
  synced.

## SDD Cycle Complete

The change `perf-cache-batching` (Change E) has been fully planned,
implemented, verified, and archived. Ready for the next change.

## Engram Traceability

- Apply progress: topic_key `sdd/perf-cache-batching/apply-progress` (#1955)
- Verify report: topic_key `sdd/perf-cache-batching/verify` (#1956)
- Archive report: topic_key `sdd/perf-cache-batching/archive-report` (#1957)
