# Tasks: docs-sync-reality

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~90 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | All 5 doc edits (D1-D5) | PR 1 | single PR; ~90 LoC; no code/tests |

## Phase 1: README.md (D1 + D4)

- [x] 1.1 Update structure tree (README.md:22-30): `core.py` -> `core/` package with
      submodules; add `tests/`, `openspec/`, `requirements-dev.txt`, `pytest.ini`.
- [x] 1.2 Update code table (README.md:167-173): `core.py` -> `core/`; fix trailing
      prose line.
- [x] 1.3 Split exit-codes table (README.md:115-122): add `| 0 | --help (ayuda) |`,
      change `| 1 | Sin argumentos / help |` -> `| 1 | Sin argumentos (no query flag) |`.

## Phase 2: openspec/AGENTS.md (D2 + D5)

- [x] 2.1 Rewrite "Testing capabilities" (63-73): pytest runner, 63 tests,
      strict_tdd:true.
- [x] 2.2 Remove "Upcoming change: fix/judgment-day-round-1" (84-128); replace with
      one-line archive pointer.
- [x] 2.3 Fix Conventions `_get_with_retry` (60-61): now raises typed `FetchError`.
- [x] 2.4 Fix file-layout tree (17-36): `core.py` -> `core/` package.
- [x] 2.5 Fix module-responsibilities table (43-44): `openpyxl` -> lazy for `app.py`
      and `cli.py`.

## Phase 3: openspec/config.yaml (D3)

- [x] 3.1 Update `testing` section (15-27): `runner: pytest`, `layers.unit: true`.
- [x] 3.2 Update `strict_tdd_reason` (10-13): remove archived-change reference; state
      current pytest + 63-tests reality.

## Phase 4: Verify

- [x] 4.1 Run `.\venv\Scripts\python.exe -m pytest -q` -- confirm 63/63 (no code
      changed).
- [x] 4.2 Visual review: each file reads correctly; no stale `core.py` references, no
      "upcoming" archived-change section, exit codes split, openpyxl marked lazy.
