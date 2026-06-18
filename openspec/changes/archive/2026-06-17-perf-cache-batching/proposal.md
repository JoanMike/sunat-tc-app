# Proposal: perf-cache-batching (Change E)

## Intent

Four performance fixes in the SQLite cache + `fetch_range` loop of
`core/__init__.py` (post-Change-A state): eliminate (P1) one SQLite
connection per row in `cache_put`, (P2) redundant DDL on every `_connect`,
(P3) the double cache read per month in `fetch_range`, and (P4) an excessive
0.3s courtesy sleep. No behavior or API breakage; pure performance.

## Scope

### In Scope
- **P1**: `cache_put_many(rows)` via `executemany` + one connection/commit; `cache_put` becomes a thin wrapper; `fetch_day`/`fetch_month` batch writes.
- **P2**: `_connect` runs `CREATE TABLE`/`CREATE INDEX` only when `CACHE_DB` does not exist (guard before `sqlite3.connect`).
- **P3**: private `_fetch_month_with_flag(y, m, use_cache) -> (rows, network_happened)`; `fetch_range` reads each month's cache once and drops `_month_requires_network`; public `fetch_month` delegates (contract preserved).
- **P4**: `time.sleep(0.3)` -> `time.sleep(0.1)` with justification comment. P3+P4 ship in the SAME commit (coupled via `network_happened`).

### Out of Scope
- Change A (`fix-data-layer-bugs`) — done/archived.
- Change B (other bugs) — done.
- Change D (`docs-sync-reality`) — done.
- Change F — any GUI work.
- Change G — lint/type-check setup.
- Any CLI surface change; any new bug; any data migration.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `data-fetch`: add `cache_put_many` batched-write requirement; add schema-DDL-only-when-missing requirement; modify the existing "Cache-hit short-circuit in `fetch_range`" requirement to single-read + 0.1s sleep.

## Approach

Single PR, ~160 LoC, one file (`core/__init__.py`). Strict TDD, RED-first. P3+P4 in one GREEN commit because the `network_happened` flag produced by the P3 helper is consumed by the P4 sleep. All four fixes are local; no GUI/CLI surface changes. Public API addition: `cache_put_many`. Removals: none (`cache_put` retained as wrapper; `fetch_month` contract unchanged; `_month_requires_network` is private -> safe to delete).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `core/__init__.py:191-207` (`_connect`) | Modified | P2 DDL guard on `CACHE_DB.exists()`. |
| `core/__init__.py:264-287` (`cache_put`) | Modified | P1; `cache_put_many` added; `cache_put` thin wrapper. |
| `core/__init__.py:324-343` (`fetch_day`) | Modified | P1 batch write. |
| `core/__init__.py:346-364` (`fetch_month`) | Modified | P1 batch write + P3 helper extraction. |
| `core/__init__.py:367-416` (`fetch_range`) | Modified | P3 single cache read; P4 sleep 0.1s. |
| `core/__init__.py:419-430` (`_month_requires_network`) | Removed | P3; folded into `_fetch_month_with_flag`. |
| `tests/test_core.py` | Added | New RED tests per item. |
| `openspec/specs/data-fetch/spec.md` | Modified (at archive) | 2 ADDED + 1 MODIFIED requirement. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| P3 breaks `test_fetch_range_cache_hit_skips_sleep` regression | Low | Option (a') preserves cache-hit -> `network_happened=False` -> skip sleep; test stays green as the RED-guard. |
| P2 file-exists-but-table-missing -> `OperationalError` | Low | Acceptable for single-user desktop app; documented known limitation. |
| P3+P4 split across commits incoherent flag wiring | Med | Ship P3+P4 in the same commit. |

## Rollback Plan

`git revert` of the single PR. No data migration (same schema, same `ON CONFLICT` upsert semantics); the DB file is untouched by the revert.

## Dependencies

- Change A (`fix-data-layer-bugs`) — archived 2026-06-17; this change builds on its post-A `core/__init__.py`.

## Success Criteria

- [ ] `pytest -q` green (63 existing + new tests).
- [ ] `test_fetch_range_cache_hit_skips_sleep` still green.
- [ ] `fetch_month` with a 20-row network response opens exactly 1 SQLite connection (not 20).
- [ ] Second `_connect` call (DB existing) does not run DDL.
- [ ] `fetch_range` reads each month's cache at most once.
- [ ] Network-month courtesy sleep is 0.1s (worst case 2.4s for a 2-year range).
- [ ] ~160 LoC, well under the 400-line review budget.
