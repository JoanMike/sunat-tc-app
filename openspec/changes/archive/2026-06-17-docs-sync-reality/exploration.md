## Exploration: docs-sync-reality

### Current State

After Changes A (`fix-data-layer-bugs`) and B (`fix-gui-lifecycle-bugs`) were archived
2026-06-17, plus the prior `fix-judgment-day-round-1` archived 2026-06-13, three
documentation files still describe pre-change reality:

- **README.md** — calls the data layer `core.py` (single file); it is now a `core/`
  package (`__init__.py`, `errors.py`, `locale.py`, `validators.py`, `messages.py`).
  The structure tree omits `core/` submodules, `tests/`, `openspec/`,
  `requirements-dev.txt`, `pytest.ini`. The exit-codes table conflates `--help`
  (exit 0) with no-args (exit 1).
- **openspec/AGENTS.md** — "Testing capabilities" says runner=NONE, strict_tdd=false;
  reality is pytest bootstrapped (63 passing) and `strict_tdd: true`. The "Upcoming
  change: fix/judgment-day-round-1" section (lines 84-128) describes an archived
  change as upcoming. The Conventions `_get_with_retry` line says it collapses
  failures to `[]`; it now raises typed `FetchError`. The module-responsibilities
  table lists `openpyxl` as a top-level import of `app.py` and `cli.py`; both now
  lazy-import it. The file-layout tree also shows `core.py`.
- **openspec/config.yaml** — `testing` section says runner=none, all layers false;
  reality is runner=pytest, unit=true. `strict_tdd_reason` references the archived
  `fix/judgment-day-round-1` cycle.

### Affected Areas

- `README.md` — structure tree (22-30), code table (167-173), exit-codes table (115-122).
- `openspec/AGENTS.md` — Testing capabilities (63-73), Upcoming-change section
  (84-128), Conventions `_get_with_retry` (60-61), File layout (17-36), Module
  responsibilities table (38-44).
- `openspec/config.yaml` — testing section (15-27), strict_tdd_reason (10-13).

### Approaches

1. **Edit stale text to match reality** — replace each drifted passage with current
   facts (core/ package, pytest+63 tests, strict_tdd:true, lazy openpyxl, split exit
   codes, remove archived-change section).
   - Pros: direct, zero runtime risk, keeps docs honest.
   - Cons: none material.
   - Effort: Low (~90 LoC of markdown/yaml).

### Recommendation

Approach 1 — there is no real alternative; the docs are simply wrong.

### Risks

- Very low — documentation-only edits; no production code or tests touched.
- `pytest -q` MUST remain 63/63 (sanity check; no code changed).

### Additional drift flagged (out of scope — proposal decides)

- `config.yaml:5` context block says "3-file split — `core.py`" — should say `core/`
  package. Outside D3's stated scope (testing section + strict_tdd_reason only).
- `config.yaml:32` `rules.proposal` still says "Judgment Day Round 1 findings must be
  addressed in this change cycle" — that cycle is archived; the rule is stale.

### Ready for Proposal

Yes — scope is fixed at D1-D5; the two flagged extras are proposed as out-of-scope
for this change.
