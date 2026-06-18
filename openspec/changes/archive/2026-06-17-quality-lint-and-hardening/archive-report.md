# Archive Report — `quality-lint-and-hardening` (Change G — FINAL)

**Change**: `quality-lint-and-hardening`
**Project**: `sunat-tc-app`
**Mode**: `hybrid` (OpenSpec filesystem + Engram traceability)
**Archived at**: 2026-06-17
**Final verdict**: PASS
**Status**: success
**Chain position**: Change G of 7 (A, B, D, E, F, G) — **the LAST change of the chain**

## Spec Sync Summary

| Domain | Action | Details | Target file |
|--------|--------|---------|-------------|
| `app-startup-and-imports` | 1 MODIFIED + 1 ADDED | MODIFIED "Acerca de" requirement to source version from `core.__version__` (supersedes Change F's `_APP_VERSION` placeholder); ADDED `--version` CLI flag requirement (prints `%(prog)s {__version__}`, exits 0, no fetch) | `openspec/specs/app-startup-and-imports/spec.md` |
| `data-fetch` | 1 MODIFIED | MODIFIED "Typed `FetchError` from `_get_with_retry`" to add `kind in kinds` validation at `__init__` (raises `ValueError` before setting attributes); added 2 new scenarios (invalid kind rejected; valid kinds construct normally) | `openspec/specs/data-fetch/spec.md` |
| (Q1 ruff, Q7 test fixture) | No spec delta | Tooling/test-infrastructure, not behavior contracts. Recorded in `specs/none.md`. | — |

No duplicate requirement names. MODIFIED blocks replaced in-place. No destructive deltas (0 REMOVED, 0 RENAMED).

## Tasks Completed

7/7 behavior tasks `[x]`:
- T1.1 RED + T1.2 GREEN — Q2 FetchError kind validation (invalid kind → ValueError; valid-kind triangulation)
- T2.1 GREEN — Q7 test fixture Toplevel-per-test + teardown (80 existing tests stayed green)
- T3.1 RED + T3.2 GREEN — Q8 `core.__version__` + `app.py`/`cli.py` wiring + `--version` flag
- T4.1 GREEN — Q1 ruff + ruff.toml + config.yaml linter flag + fix all 33 findings (0 noqa)
- T5.1 VERIFY — pytest 84/84 + ruff exit 0

Commit tasks (T1.2/T2.1/T3.2/T4.1) intentionally `[ ]` per the hard "NO git operations" user constraint — the user handles git manually.

## Test Evidence

- **pytest**: 84 passed (80 baseline + 4 new RED-first) in ~2.5s.
- **ruff**: `ruff check .` → "All checks passed!" exit 0. Zero `# noqa` lines (all 33 findings fixed: 26 auto-fix via `ruff check --fix`, 7 manual — SIM105×4 contextlib.suppress, SIM108×2 ternary, E501×4 reformat, F841×1 dead var removed).
- **Q7 regression**: all 80 pre-G tests stayed green after the Toplevel fixture refactor — transparent change.

## Deviations from Design (all non-regressions)

1. **Q2 validation placement**: placed BEFORE `super().__init__` (per spec `data-fetch.md` "BEFORE setting any instance attribute or calling super().__init__"); the apply prompt's "after" was inconsistent with spec/design/tasks. Spec is the acceptance criterion.
2. **Added valid-kind triangulation test** beyond the prompt's single invalid-kind test (strict-TDD triangulation + spec "Valid kinds still construct normally" scenario).
3. **Added `toplevel.withdraw()`** to Q7 fixture (design D3 omitted it; prompt requested it) — keeps per-test Toplevel headless, behavior-preserving.
4. **SIM105/SIM108 findings (6)** exceeded the design's "0–2" forecast; all fixed via `contextlib.suppress`/ternary (idiomatic) instead of `# noqa`. Added `import contextlib` to `app.py` + `tests/test_app.py`.

## Out-of-Scope Leakage

None. No mypy, no formatter, no Change A-F items re-touched beyond Q1 lint fixes. Scope locked to Q1/Q2/Q7/Q8.

## Chain Completion

This is the **final change** of the 7-change chained SDD plan:

| Change | Scope | Tests | Archived |
|--------|-------|-------|----------|
| A `fix-data-layer-bugs` | 8 bugs | 57 (+19) | 2026-06-17 |
| B `fix-gui-lifecycle-bugs` | 3 bugs | 63 (+6) | 2026-06-17 |
| D `docs-sync-reality` | 5 docs | 63 (sanity) | 2026-06-17 |
| E `perf-cache-batching` | 4 perf | 71 (+8) | 2026-06-17 |
| F `gui-polish-ux` | 5 UX | 80 (+9) | 2026-06-17 |
| G `quality-lint-and-hardening` | 4 quality | 84 (+4) + ruff clean | 2026-06-17 |

**Chain totals**: 29 items fixed, 46 new RED-first tests, 38 baseline → 84 passing, ruff clean. All 6 changes archived under `openspec/changes/archive/2026-06-17-*`. Active changes directory empty.

## Engram

Archive observation saved: topic_key `sdd/quality-lint-and-hardening/archive-report`, type `architecture`, capture_prompt false.
