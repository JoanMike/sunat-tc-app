# Proposal: docs-sync-reality

## Intent

Align `README.md`, `openspec/AGENTS.md`, and `openspec/config.yaml` with the
post-Changes-A+B reality. These docs still describe `core.py` as a single file, claim
no test runner exists, and reference an archived change as upcoming. The drift misleads
any agent or human reading the workspace context.

## Scope

### In Scope

- **D1** — README.md: `core.py` -> `core/` package in structure tree (lines 22-30) and
  code table (lines 167-173); add `core/` submodules, `tests/`, `openspec/`,
  `requirements-dev.txt`, `pytest.ini` to the tree.
- **D2** — AGENTS.md: rewrite "Testing capabilities" (63-73) to pytest+63 tests+
  strict_tdd:true; remove "Upcoming change: fix/judgment-day-round-1" (84-128); fix
  Conventions `_get_with_retry` line (60-61) to typed `FetchError`; update file-layout
  tree (17-36) to `core/` package.
- **D3** — config.yaml: `testing.runner` -> pytest, `testing.layers.unit` -> true,
  `strict_tdd_reason` updated to current state (no archived-change reference).
- **D4** — README.md exit-codes table (115-122): split conflated `| 1 | Sin argumentos
  / help |` into `| 0 | --help (ayuda) |` and `| 1 | Sin argumentos (no query flag) |`.
- **D5** — AGENTS.md module-responsibilities table (38-44): `openpyxl` -> lazy for both
  `app.py` and `cli.py`.

### Out of Scope

- Production code, tests, or main specs (`openspec/specs/*/spec.md`).
- Spec sync — already done during A/B archives.
- `config.yaml:5` context-block `core.py` reference and `config.yaml:32` stale
  proposal-rule (flagged in exploration; deferred to avoid scope creep).
- Changes E/F/G.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this change has no spec deltas. A single non-behavior delta (`specs/docs.md`)
records that no requirements are added, modified, removed, or renamed.

## Approach

Single "PR" of ~90 LoC of markdown/yaml edits. No TDD cycle — no behavior change, so
`strict_tdd: true` is satisfied vacuously (the `apply.tdd` rule targets
behavior-changing tasks).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Doc edit introduces a typo or inaccuracy | Low | Visual review + `pytest -q` sanity (63/63 must hold) |

## Rollback Plan

`git revert` — no runtime risk, no migration.

## Success Criteria

- [ ] All three files reflect post-Changes-A+B reality.
- [ ] `pytest -q` remains 63/63 (no code changed).
- [ ] No stale references to `fix/judgment-day-round-1` as "upcoming".
