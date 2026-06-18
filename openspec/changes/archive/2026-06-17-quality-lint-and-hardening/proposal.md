# Proposal: quality-lint-and-hardening (Change G)

> Final change of the 7-change plan. Lints the final code state and adds three
> small hardening items. Benefits from Changes A–F all being archived. Exploration:
> `openspec/changes/quality-lint-and-hardening/exploration.md`, Engram
> `sdd/quality-lint-and-hardening/explore` (#1969).

## Intent

Final quality pass before the plan closes: (1) introduce a `ruff` linter over the
final code state, (2) validate `FetchError.kind` at construction so the `kinds`
tuple is enforced rather than documentary, (3) isolate GUI tests by building each
`SunatTCApp` on a per-test `tk.Toplevel` instead of stacking widgets on a shared
module-scoped root, and (4) centralize `__version__` in `core` and surface a
`--version` CLI flag — superseding the temporary `_APP_VERSION` placeholder from
Change F.

## Scope

### In Scope
- **Q1 — ruff**: add `ruff` to `requirements-dev.txt`; create `ruff.toml`
  (`target-version = "py39"`, `line-length = 100`, `select = [E, F, W, I, UP, B, SIM]`);
  install in venv; run `ruff check .` over the FINAL state; fix trivial findings,
  `# noqa: <code>  # <reason>` for non-trivial; flip
  `openspec/config.yaml` `testing.quality.linter` to
  `{ available: true, command: "ruff check ." }`.
- **Q2 — FetchError kind validation**: `FetchError.__init__` raises `ValueError`
  when `kind not in self.kinds`; rewrite the existing unknown-kind-fallback test
  to bypass `__init__` via `FetchError.__new__` so the fallback branch stays covered.
- **Q7 — GUI test fixture isolation**: `app` fixture builds
  `SunatTCApp(tk.Toplevel(hidden_root))` per test + `toplevel.destroy()` teardown;
  `hidden_root` stays module-scoped (Python 3.14 `tcl_findLibrary` workaround).
- **Q8 — centralized `__version__` / `--version`**: `core.__version__ = "1.0.0"`
  (single source); `app.py` imports and uses it in `_show_about` (delete
  `_APP_VERSION`); `cli.py` imports it and adds `--version`
  (`action="version"`); spec delta superseding the `_APP_VERSION` requirement.

### Out of Scope
- mypy / any type-checker; black/blue or any formatter.
- Any Change A–F item; any new behavior beyond Q1/Q2/Q7/Q8.
- Widening the production signature `root: tk.Tk` (Q7 is test-only).

## Capabilities

> Contract for `sdd-spec`. Research performed against `openspec/specs/`.

### New Capabilities
- None.

### Modified Capabilities
- `app-startup-and-imports`: the "Acerca de" requirement (Change F) is MODIFIED to
  source the version from `core.__version__` (single source) instead of a local
  `_APP_VERSION` constant; an ADDED requirement covers the `--version` CLI flag.
- `data-fetch`: the typed `FetchError` requirement (Change A) is MODIFIED to add
  kind validation at construction (`kind in kinds` else `ValueError`).
- No-delta note: Q1 (ruff) and Q7 (test fixture) are tooling / test-infra, not
  behavior contracts — recorded in `specs/none.md`.

## Approach

Single PR, ~120 LoC. Apply order is fixed: **Q2 → Q7 → Q8 → Q1**, because Q1 lints
the FINAL state (running ruff before later edits would re-introduce findings).
Q2 and Q8 are RED-first (strict TDD). Q7 is a test refactor whose GREEN proof is
the existing 80 tests staying green (no new RED). Q1 is tooling whose gate is
`ruff check .` exiting 0 (no RED test).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `requirements-dev.txt` | Modified | add `ruff>=0.6.0` (Q1) |
| `ruff.toml` | New | linter config (Q1) |
| `openspec/config.yaml:23` | Modified | `linter.available` → `true`, `command` → `"ruff check ."` (Q1) |
| `core/errors.py:17-20` | Modified | `__init__` kind validation (Q2) |
| `core/__init__.py:28,~31` | Modified | `from typing` → `collections.abc` (UP035); add `__version__ = "1.0.0"` (Q8) |
| `app.py:35,41-57,86-88,632,1124` | Modified | UP035 import; import `__version__`; delete `_APP_VERSION`; use `__version__` in `_show_about`; fix E501 (Q1/Q8) |
| `cli.py:32-44,47-100` | Modified | import `__version__`; add `--version` flag (Q8) |
| `tests/test_messages.py:91-103` | Modified | rewrite unknown-kind-fallback test via `__new__` (Q2) |
| `tests/test_app.py:53-71` | Modified | `app` fixture → Toplevel-per-test + teardown (Q7) |
| `tests/test_core.py` | Modified | add `test_fetch_error_invalid_kind_raises_valueerror`, `test_core_has_version` (Q2/Q8) |
| `tests/test_cli.py` | Modified | add `test_cli_version_flag_exits_0` (Q8) |
| `tests/test_app.py:~767-789` | Modified | strengthen `test_show_about_displays_version` to assert `core.__version__` (Q8) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Q2 breaks `tests/test_messages.py:91-103` (constructs `FetchError(kind="alien_invasion")`) | High (certain) | Mandatory in-same-change rewrite via `FetchError.__new__`; keeps fallback branch covered. |
| Q7 fixture change breaks an existing Tk test (event-drain timing) | Med | Run `pytest -q` immediately after the edit; suspect `hidden_root.update()` vs `Toplevel.after`; fix with `toplevel.update()` in draining tests if needed. Leave `test_geometry_tclerror_falls_back` on `hidden_root` (monkeypatches `tk.Tk.geometry`). |
| Q1 ruff finding count is a manual estimate (ruff not installed at explore time) | Med | Apply installs ruff and runs `ruff check .` for the real count; fix trivial, noqa+justify non-trivial; do NOT relax the rule set to hide noise. |
| Q8 spec drift if the `_APP_VERSION`→`core.__version__` delta is skipped | Low | sdd-spec writes the MODIFIED delta (this proposal's Capabilities section locks it in). |
| `ruff check --fix` mutates source (safe fixes) | Low | Review the diff before committing; no unintended rewrite. |

## Rollback Plan

Single PR → `git revert` of the change commit(s). Layer isolation:
- Q2 lives in `core/errors.py` + one test rewrite → revert restores the un-validated `__init__`.
- Q7 lives entirely in `tests/test_app.py` `app` fixture → revert restores the shared-root stacking.
- Q8 lives in `core/__init__.py`, `app.py`, `cli.py` → revert restores `_APP_VERSION` and drops `--version`.
- Q1 (`requirements-dev.txt`, `ruff.toml`, `config.yaml`, trivial fixes/noqa) is removable without touching behavior.
- No data migrations; cache and state are unchanged.

## Dependencies

- No new runtime deps. New dev dep: `ruff>=0.6.0` (Q1).
- No DB schema changes; no API contract changes.
- No dependency on a specific prior change; benefits from A–F being archived (final-state lint).

## Success Criteria

- [ ] `.\venv\Scripts\python.exe -m pytest -q` is green (80 existing + new Q2/Q8 tests).
- [ ] `ruff check .` exits 0 over the final code state.
- [ ] `FetchError("bogus")` raises `ValueError`; valid kinds still construct.
- [ ] `cli.py --version` prints `<prog> 1.0.0` to stdout and exits 0.
- [ ] `core.__version__ == "1.0.0"`; `app.py` no longer defines `_APP_VERSION`.
- [ ] `openspec/config.yaml` `testing.quality.linter.available` is `true`.
- [ ] Spec deltas merged: `_APP_VERSION` requirement superseded by `core.__version__` + `--version`.

## Review Workload Forecast

~120 LoC net, single PR. Additions + deletions well under the 400-line budget.
**Chained PRs recommended: No.** **400-line budget risk: Low.**
