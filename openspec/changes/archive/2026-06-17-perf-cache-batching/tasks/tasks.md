# Tasks: perf-cache-batching (Change E)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~160 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-always (confirm single PR at apply) |
| Chain strategy | size-exception (single PR) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | P1 batched writes | PR 1 | base: post-A main; RED+GREEN one commit |
| 2 | P2 DDL guard | PR 1 | independent of P1; RED+GREEN one commit |
| 3 | P3+P4 single-read + 0.1s sleep | PR 1 | same commit (coupled via `network_happened`); base: main |

All three units land in ONE PR; commit granularity is per unit, except P3+P4 share a commit.

## Phase 1: P1 — Batched cache writes

- [x] T1.1 RED — add to `tests/test_core.py`: `test_cache_put_many_uses_one_connection` (monkeypatch `core._connect` counter; insert 20 rows; assert 1 connection), `test_cache_put_many_upserts_on_conflict`, `test_cache_put_still_works_single_row`, `test_fetch_month_batches_cache_writes` (stub `_get_with_retry` -> 20 rows; assert `cache_put_many` called once).
- [x] T1.2 GREEN — in `core/__init__.py`: implement `cache_put_many(rows, source="apis.net.pe")` (one `_connect`, `executemany`, one `commit`); rewrite `cache_put` (264-287) as thin wrapper; batch writes in `fetch_day` (341-342) and `fetch_month` (362-363). Run `pytest -q`.

## Phase 2: P2 — DDL guard in `_connect`

- [x] T2.1 RED — add `test_connect_skips_ddl_when_db_exists` (pre-create `CACHE_DB`; spy `conn.execute` -> assert no `CREATE TABLE`/`CREATE INDEX` on the second `_connect`) and `test_connect_runs_ddl_when_db_missing` (fresh tmp dir -> assert DDL runs once).
- [x] T2.2 GREEN — in `core/__init__.py:191-207`: add `if not CACHE_DB.exists():` DDL block before `sqlite3.connect(CACHE_DB)`. Run `pytest -q`.

## Phase 3: P3+P4 — Single cache read + 0.1s sleep (SAME COMMIT)

- [x] T3.1 RED — add `test_fetch_range_reads_cache_once_per_month` (spy `cache_get_month`; assert <= 1 call per month in a 2-month range) and `test_fetch_range_sleeps_0_1s_on_network_month` (cache miss; monkeypatch `core.time`; assert `sleep_calls == [0.1]` per network month, not `[0.3]`). Confirm existing `test_fetch_range_cache_hit_skips_sleep` stays green (regression guard).
- [x] T3.2 GREEN — in `core/__init__.py`: add private `_fetch_month_with_flag(year, month, use_cache) -> (rows, network_happened)`; rewrite `fetch_month` (346-364) to delegate (return only rows); rewrite `fetch_range` loop (398-412) to call the helper once per month and read `network_happened` from it; delete `_month_requires_network` (419-430); change `time.sleep(0.3)` -> `time.sleep(0.1)` with justification comment. Run `pytest -q`. (T3.1 + T3.2 = ONE commit.)

## Phase 4: Verify

- [x] T4.1 VERIFY — run `.\venv\Scripts\python.exe -m pytest -q`; assert all green (63 existing + new). Confirm `test_fetch_range_cache_hit_skips_sleep` green. Confirm review budget (~160 LoC) not exceeded.
