# Exploration: quality-lint-and-hardening (Change G)

> Final change of the 7-change chained plan. Lints the final code state and
> adds two small hardening items + one test-isolation refactor. No dependency
> on a specific prior change, but benefits from A–F all being archived.
>
- **Items (fixed scope — do not add):** Q1 (ruff), Q2 (`FetchError.kind` validation), Q7 (test fixture isolation), Q8 (`__version__` / `--version`).
- **Out of scope:** mypy / type-checker, black/blue formatter, any Change A–F item, any new behavior.
- **Strict TDD:** Q2 & Q8 are RED-first; Q7 is a test refactor (existing-green = proof); Q1 is tooling (gate = `ruff check .` clean, no RED test).

## Current State

- **No linter/type-checker/formatter.** `openspec/config.yaml:23-25` declares `linter / type_checker / formatter` all `{ available: false, command: "" }`. `requirements-dev.txt` has only `pytest`, `pytest-mock`, `requests-mock`. No `pyproject.toml` / `setup.cfg` / `setup.py` / `tox.ini` / `ruff.toml` exist (glob-confirmed) → a standalone `ruff.toml` is the right home.
- **`FetchError` does not validate `kind`.** `core/errors.py:15` defines `kinds = ("network","http_4xx","http_5xx","parse","rate_limit","input")`; `__init__` (`core/errors.py:17-20`) accepts ANY string. `FetchError("bogus")` silently succeeds. The `kinds` tuple is documentation only, never enforced.
- **GUI tests stack on a shared module-scoped root.** `tests/test_app.py:32-50` `hidden_root` is `scope="module"` (a Python 3.14 Windows `tcl_findLibrary` re-creation bug forces a single root). The `app` fixture (`tests/test_app.py:53-71`) builds `SunatTCApp(hidden_root)` for every test with no teardown → widgets accumulate on the shared root across all ~27 tests.
- **No `__version__`.** `app.py:88` has `_APP_VERSION = "1.0.0"` (the Change F temp placeholder, documented as "Change G centralizes later"). Used only at `app.py:632` inside `_show_about`. No `__version__` anywhere (`grep`-confirmed). `cli.py` has no `--version`. The archived spec `openspec/specs/app-startup-and-imports/spec.md:203-211` currently REQUIRES `_APP_VERSION` — Q8 supersedes that requirement (spec delta needed).

## Affected Areas

- `requirements-dev.txt` — add `ruff`. (Q1)
- `ruff.toml` (NEW) — config. (Q1)
- `openspec/config.yaml:23` — flip `linter.available` → `true`, `command` → `"ruff check ."`. (Q1)
- `core/errors.py:17-20` — add `kind` validation in `__init__`. (Q2)
- `tests/test_messages.py:91-103` — **`test_format_fetch_error_unknown_kind_fallback` constructs `FetchError(kind="alien_invasion")` (line 93); Q2 breaks it → must rewrite to bypass `__init__`.** (Q2 blast radius)
- `tests/test_app.py:53-71` — rewrite `app` fixture to use `tk.Toplevel(hidden_root)` + teardown. (Q7)
- `core/__init__.py` — add `__version__ = "1.0.0"` (single source). (Q8)
- `app.py:88` (remove `_APP_VERSION`), `app.py:41-57` (import `__version__`), `app.py:632` (use `__version__`). (Q8)
- `cli.py:32-44` (import `__version__`), `cli.py:47-100` `_build_parser` (add `--version`). (Q8)
- `tests/test_core.py` (Q8 RED `test_core_has_version`), `tests/test_cli.py` (Q8 RED `test_cli_version_flag_exits_0`), `tests/test_app.py:767-789` (strengthen `test_show_about_displays_version` → assert `core.__version__`, not literal `"1.0.0"`). (Q8)
- `openspec/specs/app-startup-and-imports/spec.md` — spec delta: replace the `_APP_VERSION` requirement with the `core.__version__` + `--version` requirement. (Q8, spec phase)

## Approaches

### Q1 — ruff

**Choice A (rule set):** starter set `{E, F, W, I, UP, B, SIM}` at `line-length = 100`, `target-version = "py39"`.
- Pros: pragmatic coverage; catches real bugs (B), modernization (UP), simplifications (SIM); matches "match existing code" (max real line is 114 at one site, rest ≤100).
- Cons: `UP035` will flag `from typing import Callable[, Iterable]` (2 sites) → needs 2 trivial import-path edits (`→ collections.abc`).
- Effort: Low.

**Choice A′ (minimal rule set):** `{E, F, W, I}` only (drop UP/B/SIM).
- Pros: zero modernization churn; smallest diff.
- Cons: leaves bug-detection/simplification on the table; defers value.
- Effort: Low. — Rejected (leaves too much on the table for the "final hardening" change).

**Choice B (fix-vs-noqa policy):** run `ruff check --fix` for SAFE fixes (UP035, isort) → manually resolve E501 + any residual → `# noqa: <code>` with a justification comment ONLY for genuinely unavoidable cases.
- Pros: minimal noise; every noqa is auditable.
- Cons: needs a manual review pass.
- Effort: Low.

**Choice B′ (noqa-everywhere):** noqa all findings to get green fast.
- Rejected — defeats the purpose of linting and leaves unjustified suppressions.

**Predicted finding inventory** (manual analysis — ruff not installed yet; apply phase installs it):
- `E501` ×1 — `app.py:1124` (114 chars, the `askyesno` "¿Abrir la carpeta?" line). Fix by extracting the message to a local / splitting the f-string (trivial, in-scope). noqa only as last resort.
- `UP035` ×2 — `app.py:35` `from typing import Callable` and `core/__init__.py:28` `from typing import Callable, Iterable`. Safe auto-fix → `from collections.abc import ...`. SAFE because all uses are annotations only and `from __future__ import annotations` makes them strings (no runtime eval).
- `F401` — none expected: re-exports in `core/__init__.py:36-39` already carry justified `# noqa: F401`; `Callable`/`Iterable` are used (`app.py:811`, `core/__init__.py:279,430`).
- `I` (isort) — likely clean; import blocks are already `import`-then-`from`, third-party (`requests`) and first-party (`core`) correctly sectioned.
- `B` / `SIM` — expect 0–2 low-severity (no mutable defaults seen; no `dict.keys()` membership); handle ad hoc in apply.
- Net: a SMALL finding set — consistent with the ~120 LoC / single-PR framing.

### Q2 — `FetchError.kind` validation

**Approach:** in `__init__`, `if kind not in self.kinds: raise ValueError(f"Invalid FetchError kind {kind!r}; must be one of {self.kinds}")` before `super().__init__`. RED test `test_fetch_error_invalid_kind_raises_valueerror` (in `tests/test_core.py`): `with pytest.raises(ValueError): FetchError("bogus")`.
- Pros: catches typos at raise-time (e.g. `kind="htttp_4xx"`); defense-in-depth.
- Cons: **invalidates `tests/test_messages.py:93`** (`FetchError(kind="alien_invasion")`), which exists to cover `format_fetch_error`'s unknown-kind fallback (`core/messages.py:25-27,38`).
- Effort: Low — but see the test rewrite below.

**Required companion test rewrite** (NOT optional — Q2 breaks the existing test):
`test_format_fetch_error_unknown_kind_fallback` must construct the error bypassing validation so the fallback branch stays covered:
```python
exc = FetchError.__new__(FetchError)
exc.kind = "alien_invasion"
Exception.__init__(exc, "raw text")
```
The `_GENERIC_FALLBACK` stays in production (defense-in-depth: a new `kinds` entry without a matching `_FETCH_ERROR_MESSAGES_ES` key, or reconstruction via pickle, would still hit it).

### Q7 — test fixture isolation

**Choice A — Toplevel-per-test (RECOMMENDED):** `app` fixture builds `SunatTCApp(tk.Toplevel(hidden_root))` and `yield`s; teardown `toplevel.destroy()`.
- Pros: per-test fresh window + fresh app; single shared root preserved (no 3.14 bug); strong isolation.
- Cons: changes the test-only layer; must re-verify the full suite.
- Effort: Low.

**Choice B — destroy-and-recreate `tk.Tk()` per test:** REJECTED — hits the Python 3.14 `tcl_findLibrary` re-creation bug on Windows (the exact reason `hidden_root` is module-scoped).

**Choice C — `tk.Frame(hidden_root)` per test:** REJECTED — `SunatTCApp.__init__` calls `title/geometry/minsize/protocol` (`app.py:234,243,246,249,250`) which are `tk.Wm` methods; `Frame` is not a toplevel window and lacks them.

**Choice D — keep shared root, manually destroy app widgets in teardown:** REJECTED — fragile widget-name management; does not isolate `bind_all` / `protocol` handlers.

**Compatibility audit for Choice A** — every `self.root.*` call in `SunatTCApp` is valid on `tk.Toplevel` (Toplevel inherits `tk.Wm` + `tk.Misc`): `title`, `geometry`, `minsize`, `protocol("WM_DELETE_WINDOW", …)`, `bind_all`, `after`, `update`, `update_idletasks`, `destroy` (all 12 call sites, `app.py:234-1023`). `bind_all` is interpreter-wide → works regardless of parent. **Do NOT widen the production signature `root: tk.Tk`** (`app.py:232`) — Q7 is test-only; `from __future__ import annotations` makes the hint a non-enforcing string and ruff (no type checker) will not flag a Toplevel passed for `tk.Tk`. Widening is a mypy concern → out of scope.

**Deliberate non-migration:** `test_geometry_tclerror_falls_back` (`tests/test_app.py:158-195`) builds `SunatTCApp(hidden_root)` directly and monkeypatches `tk.Tk.geometry` (`:185`). It MUST stay on `hidden_root` — the `tk.Tk.geometry` patch does not affect `tk.Toplevel`, so migrating it would silently un-test the fallback. It is the only test that still stacks directly on the shared root (a single one-off, acceptable; strictly better than the pre-Q7 state where every app-fixture test stacked).

**Cross-test event draining:** tests that drain the loop via `hidden_root.update()` / `update_idletasks()` (e.g. `test_stale_callback_dropped` `:367-368`) still work after Choice A — Tk `update()` processes ALL interpreter events including a `Toplevel.after(0, …)` callback. This is the #1 empirical risk to verify by running the suite.

**Side benefit:** the `_on_close` tests (`tests/test_app.py:502,524,553`) monkeypatch `app.root.destroy` to a no-op to protect the shared root; after Choice A `app.root` is the per-test Toplevel, so those protective patches become unnecessary (but harmless) — the shared root is never at risk because `_on_close` only destroys `self.root`.

### Q8 — `__version__` / `--version`

**Approach:** single source `__version__ = "1.0.0"` in `core/__init__.py`; `app.py` imports it and uses it in `_show_about` (delete the temp `_APP_VERSION`); `cli.py` imports it and adds `p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")`.
- Pros: one source of truth; argparse `action="version"` prints to stdout and exits 0 for free.
- Cons: supersedes the archived `_APP_VERSION` spec requirement → spec delta required.
- Effort: Low.
- RED tests: `test_core_has_version` (`assert core.__version__ == "1.0.0"`); `test_cli_version_flag_exits_0` (`cli.run(["--version"])` → `SystemExit(0)`, captured stdout contains `"1.0.0"`); strengthen `test_show_about_displays_version` to assert `core.__version__ in message` (not the literal `"1.0.0"`).

## Recommendation

- **Q1:** Choice A + Choice B. `ruff.toml` with `{E,F,W,I,UP,B,SIM}`, `line-length=100`, `target-version="py39"`; `ruff>=0.6.0` in `requirements-dev.txt`; install in venv; `ruff check --fix` for safe fixes, then resolve E501 (`app.py:1124`) by reformat and the UP035 import-path edits; noqa-with-justification only as last resort. Flip `config.yaml:23`. Gate: `ruff check .` exits 0.
- **Q2:** Add the `ValueError` guard; RED test first; **rewrite `test_format_fetch_error_unknown_kind_fallback` to construct via `__new__`** so the fallback branch stays covered.
- **Q7:** Choice A — Toplevel-per-test + teardown. Run the full suite as the GREEN proof; leave `test_geometry_tclerror_falls_back` on `hidden_root`.
- **Q8:** Centralize in `core.__version__`; remove `_APP_VERSION`; add `--version`; 3 RED tests; spec delta for `app-startup-and-imports`.

**Review-budget forecast:** ~120 LoC net across one PR → additions+deletions well under the 400-line budget. **Chained PRs recommended: No.** **400-line budget risk: Low.**

## Risks

- **Q7 — fixture change could break existing tests** (highest risk). The full 80-test suite MUST pass after switching `app` to a Toplevel. Key empirically-unverified point: `hidden_root.update()` draining a `Toplevel.after(0,…)` callback (`test_stale_callback_dropped`). Mitigation: run `pytest -q` immediately after the fixture edit; if any Tk test fails, the likely culprit is event-drain timing, fixable with `toplevel.update()` in the draining tests.
- **Q2 — breaks `tests/test_messages.py:91-103`.** Must rewrite that test in the same change or the suite goes red. Mitigation: the `__new__` rewrite is small and keeps the fallback covered.
- **Q1 — ruff finding count is a manual estimate** (ruff not installed at explore time). Apply phase must `pip install ruff` and run `ruff check .` to get the real count. If UP035/SIM surface more than predicted, decide per-finding (fix if trivial+safe, else noqa-with-justification) — do NOT relax the rule set to hide noise.
- **Q1 — `ruff check --fix` mutates source** (safe fixes only). Acceptable in apply; review the diff before committing so no unintended rewrite slips in.
- **Q8 — spec drift.** The archived `app-startup-and-imports` spec still mandates `_APP_VERSION`. If the spec delta is skipped, the archive step leaves a stale requirement. Mitigation: sdd-spec MUST write the `_APP_VERSION`→`core.__version__` delta.
- **Cross-item ordering:** Q1 (ruff) lints the FINAL state, so apply Q2/Q7/Q8 code edits first, then run `ruff check .` last — otherwise ruff flags will be re-introduced by later edits.

## Ready for Proposal

**Yes.** Scope is fixed (Q1/Q2/Q7/Q8), sites confirmed, blast radii mapped (notably the Q2→test_messages and Q8→spec couplings), and the work fits a single sub-400-line PR. Recommend the orchestrator tell the user: "Change G is the final hardening pass — ruff + FetchError kind validation + GUI test isolation + centralized __version__/--version; ~120 LoC, one PR, ready to propose."
