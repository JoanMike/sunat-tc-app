# Exploration: perf-cache-batching (Change E)

Scope: 4 performance items in `core/__init__.py` (P1–P4). ~160 LoC, single PR.
Depends on Change A (`fix-data-layer-bugs`, archived 2026-06-17) — touches the same
`core/__init__.py` post-A state. Read-only exploration; no production code modified.

## Current State

`core/__init__.py` (post-A, 479 lines) integrates SUNAT fetching with a SQLite cache at
`%APPDATA%/sunat-tc-app/cache.db`. Four hot-path inefficiencies, all concentrated in the
cache + fetch layer:

- **P1 — `cache_put` (lines 264–287)** opens a SQLite connection PER ROW: `_connect()` →
  `INSERT … ON CONFLICT DO UPDATE` → `commit()` → `close()`. The two callers,
  `fetch_day` (line 342) and `fetch_month` (line 363), loop over rows calling `cache_put`
  per row. A 2-year range with a full cache miss ≈ 24 months × ~20 rows ≈ 480 connections.
- **P2 — `_connect` (lines 191–207)** runs `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX
  IF NOT EXISTS` + `commit()` on EVERY call, even when the DB file already exists and the
  schema is initialized. Every `cache_get`/`cache_put`/`cache_count`/`cache_clear` pays
  this DDL tax.
- **P3 — `fetch_range` (lines 367–416)** double-reads the cache per month: line 398 calls
  `_month_requires_network(y, m, …)` (which calls `cache_get_month` at line 429) and then
  line 399 calls `fetch_month(y, m, …)` (which calls `cache_get_month` again at line 355).
  Two identical `SELECT … WHERE fecha BETWEEN …` queries per month.
- **P4 — `fetch_range` line 412**: `if network_happened: time.sleep(0.3)`. A 2-year
  full-miss range = 24 × 0.3s = 7.2s of pure courtesy sleep.

## Affected Areas

- `core/__init__.py:191–207` (`_connect`) — P2 DDL guard.
- `core/__init__.py:264–287` (`cache_put`) — P1; new `cache_put_many` added near here.
- `core/__init__.py:324–343` (`fetch_day`) — P1 caller; switch to `cache_put_many`.
- `core/__init__.py:346–364` (`fetch_month`) — P1 caller + P3 refactor surface; new
  private `_fetch_month_with_flag` helper extracted here.
- `core/__init__.py:367–416` (`fetch_range`) — P3 (drop `_month_requires_network` call,
  use helper) + P4 (sleep value 0.3 → 0.1).
- `core/__init__.py:419–430` (`_month_requires_network`) — P3; becomes dead code after
  refactor (delete, or fold into the helper).
- `tests/test_core.py:139–147` (`test_cache_put_and_get_roundtrip`) — P1; single-row
  `cache_put` contract MUST still pass.
- `tests/test_core.py:154–175` (`test_fetch_range_cache_hit_skips_sleep`) — **P3/P4
  regression constraint** (see Risks).
- `openspec/specs/data-fetch/spec.md` — mentions `cache_put` by name (line 78); spec
  delta in sdd-spec must add `cache_put_many` requirement.

## Approaches

### P1 — batched cache writes

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **A. Keep `cache_put` independent, add `cache_put_many`** | New `cache_put_many(rows: Iterable[tuple])` using ONE connection + `executemany` + single `commit`. `fetch_day`/`fetch_month` collect rows and call it once. `cache_put` unchanged. | Zero risk to existing single-row tests; clear separation | Two INSERT SQL strings (duplication) | Low |
| **B. `cache_put` delegates to `cache_put_many`** (recommended) | `cache_put_many(rows)` is the single implementation; computes `fetched_at` once per batch. `cache_put(fecha, compra, venta, source)` becomes a thin wrapper: `cache_put_many([(fecha, compra, venta, source)])`. | One INSERT SQL string (DRY); consistent batch `fetched_at` (matches "rows fetched together" semantics); existing `cache_put` tests pass unchanged | Tiny per-call list-wrap overhead on single-row path (negligible) | Low |

API shape: `cache_put_many(rows: Iterable[tuple]) -> None` where each tuple is
`(fecha, compra, venta, source)`; `fetched_at` computed once inside. SQLite `executemany`
supports `INSERT … ON CONFLICT DO UPDATE` (upsert) — verified against current SQL.

### P2 — skip DDL when schema already initialized

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **A. Module-level `_schema_initialized` flag + lock** | First call runs DDL under a lock, sets flag; subsequent calls skip. | Explicit guard | Shared mutable state; needs a lock; flag stays True if DB file deleted at runtime (DDL won't re-run) → stale | Medium |
| **B. `CACHE_DB.exists()` check per call** (recommended) | Inside `_connect`: `if not CACHE_DB.exists(): <run DDL>` before `sqlite3.connect`. `Path.exists()` is a cheap syscall. | No shared state → thread-safe by design; no lock; correctly re-runs DDL if the DB file is deleted between calls | If the file exists but the `rates` table is missing (manual tampering / foreign process created the file), DDL is skipped. Not a realistic scenario for this single-user single-process app; `CREATE TABLE IF NOT EXISTS` was the only thing that would have healed it | Low |

Note: `sqlite3.connect` creates the file if missing, so the `exists()` check MUST happen
before `connect`. Two threads racing on a missing file both see `not exists()`, both run
DDL — idempotent via `IF NOT EXISTS`, no corruption.

### P3 — eliminate the double cache read per month

The `network_happened` flag (from `_month_requires_network`) drives P4's `time.sleep`.
P3 and P4 interact: any P3 refactor MUST still produce an accurate `network_happened`
on the cache-hit path (False → skip sleep) and cache-miss path (True → sleep).

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **(a) `fetch_month` returns `(rows, network_happened)`** | Change `fetch_month` signature. | Single read; flag is free | **BREAKING** — `fetch_month` is public (GUI/CLI/tests call it). Reject. | High |
| **(a') Private `_fetch_month_with_flag` helper** (recommended) | Extract `_fetch_month_with_flag(year, month, use_cache) -> tuple[list[dict], bool]` that does the cache check ONCE and returns rows + whether network happened. `fetch_range` calls it once per month and drops `_month_requires_network` entirely. Public `fetch_month` delegates to it and returns only the rows (contract preserved). | Single cache read per month; `network_happened` from the same call; threshold logic (`MIN_DAYS_FOR_CACHED_MONTH`) lives in ONE place; `fetch_month` contract unchanged | One new private function | Low-Med |
| **(b) Inline cache check in `fetch_range`, add `_fetch_month_internal`** | `fetch_range` checks cache; on hit uses cached rows directly, on miss calls an internal skip-cache `fetch_month`. | Single read | Duplicates the `len(cached) >= MIN_DAYS_FOR_CACHED_MONTH` + sort logic in `fetch_range`; threshold logic now in two places | Medium |
| **(c) `_month_requires_network` returns `(bool, cached_rows)`** | Widen the predicate to also return the cached dict; `fetch_range` reuses it on hit and calls `fetch_month(use_cache=False)` on miss. | Single read on hit path; small change | Splits cache-check logic between the predicate and `fetch_range`; on the miss path `fetch_month(use_cache=False)` skips its cache read (good) but the predicate's read is now "wasted" only when a miss is expected | Medium |

### P4 — reduce courtesy sleep 0.3s → 0.1s

Single-line change at `fetch_range` line 412. No design fork; the spec delegates the exact
value to design. Justify in a code comment: `apis.net.pe` is a public free API; 0.1s is
still polite; the existing exponential backoff in `_get_with_retry` already handles
transient overload (429/5xx). Worst case drops 7.2s → 2.4s for a 2-year full miss.

## Recommendation

- **P1 → Option B**: `cache_put_many` as the single implementation; `cache_put` thin
  wrapper. DRY, consistent batch `fetched_at`, zero test churn.
- **P2 → Option B**: `CACHE_DB.exists()` gate inside `_connect`, before `connect()`.
  Thread-safe by design, no shared state.
- **P3 → Option (a')**: private `_fetch_month_with_flag` helper; `fetch_range` calls it
  once per month; delete `_month_requires_network`; public `fetch_month` delegates and
  keeps its return contract.
- **P4 → `time.sleep(0.1)`** with the justification comment above.

All four are local to `core/__init__.py`. No GUI/CLI surface changes. Public API
additions: `cache_put_many` (new). Public API removals: none (`cache_put` retained as
wrapper; `fetch_month` contract unchanged; `_month_requires_network` is private → safe to
delete). Net: ~160 LoC, single PR, comfortably under the 400-line review budget.

## Risks

- **P2 thread-safety / file-exists-but-table-missing edge case** (Option B): if the DB
  file exists but the `rates` table is absent (manual tampering), DDL is skipped and the
  first `cache_*` call raises `sqlite3.OperationalError: no such table: rates`. Acceptable
  for a single-user desktop app; documented as a known limitation. Mitigation if ever
  needed: fall back to `CREATE TABLE IF NOT EXISTS` unconditionally on
  `OperationalError`. Not in scope for this change.
- **P3 regression — `test_fetch_range_cache_hit_skips_sleep` MUST still pass**. This test
  (test_core.py:154–175) pre-populates Jan 2024 with 20 days (> `MIN_DAYS_FOR_CACHED_MONTH`
  = 15), monkeypatches `core.time` to record `sleep` calls, and asserts `sleep_calls == []`
  on a cache-hit `fetch_range`. Option (a') preserves this: when the cache is complete,
  `_fetch_month_with_flag` returns `(rows, network_happened=False)` → `fetch_range` skips
  `time.sleep`. This test is the primary RED-guard for P3 — it MUST stay green; new tests
  assert the single-read property.
- **P4 does NOT break the cache-hit-skip-sleep test**: P4 only changes the sleep VALUE on
  the network-needed path; the cache-hit path skips sleep entirely via
  `if network_happened:`. The test monkeypatches the whole `core.time` module and asserts
  an empty list, so it is value-agnostic. Safe.
- **P3/P4 interaction**: `network_happened` is computed by the P3 helper AND consumed by
  the P4 sleep. The two items MUST be implemented together (same task/commit) to keep the
  flag wiring coherent — do not split P3 and P4 across commits.
- **Strict TDD (`strict_tdd: true`)**: every item MUST go RED-first. Suggested failing
  tests before GREEN:
  - P1: assert `fetch_month` (multi-row network response) calls `_connect` exactly once
    (spy on `core._connect`); assert `cache_put_many` round-trips N rows.
  - P2: assert a second `_connect` (DB already existing) does NOT execute `CREATE TABLE`
    (spy on `conn.execute`).
  - P3: assert `cache_get_month` is called at most once per month in `fetch_range` (spy);
    keep `test_fetch_range_cache_hit_skips_sleep` green as the behavior guard.
  - P4: assert the network-needed path records `time.sleep(0.1)` (not 0.3) via the
    existing monkeypatch pattern.
- **Review-budget**: ~160 LoC, one file, single PR — Low risk of exceeding 400 lines.

## Ready for Proposal

**Yes.** Scope is fixed (P1–P4), sites verified, design forks resolved with a
recommendation per item, and the key regression constraint (`test_fetch_range_cache_hit_skips_sleep`)
is identified. The orchestrator should tell the user: Change E is a self-contained
`core/__init__.py`-only perf batch (no UI/CLI/docs), proceeds to `sdd-propose` next, and
P3+P4 must ship in the same commit. Open question for the user (only if they care): confirm
the 0.1s courtesy value is acceptable — otherwise the spec's delegated value stands.
