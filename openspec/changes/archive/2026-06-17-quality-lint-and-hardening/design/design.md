# Design: quality-lint-and-hardening (Change G)

> Final hardening pass. Exploration: `exploration.md` / Engram
> `sdd/quality-lint-and-hardening/explore` (#1969). Specs: deltas for
> `app-startup-and-imports` and `data-fetch`; `none.md` for Q1/Q7.

## Goal

Land four low-risk items in one PR (~120 LoC): a `ruff` linter gate over the
final code state, `FetchError.kind` construction validation, per-test GUI
fixture isolation via `tk.Toplevel`, and a centralized `core.__version__` with a
`--version` CLI flag. No new behavior beyond these four.

## Files (exact line ranges, confirmed by read)

| Item | File | Lines | Change |
|------|------|-------|--------|
| Q2 | `core/errors.py` | 15-20 | add `kind` validation in `__init__` |
| Q2 | `tests/test_messages.py` | 91-103 | rewrite `test_format_fetch_error_unknown_kind_fallback` via `__new__` |
| Q2 | `tests/test_core.py` | (append) | new `test_fetch_error_invalid_kind_raises_valueerror` |
| Q7 | `tests/test_app.py` | 32-50 | `hidden_root` fixture — UNCHANGED (keep module-scoped) |
| Q7 | `tests/test_app.py` | 53-71 | `app` fixture → Toplevel-per-test + teardown |
| Q8 | `core/__init__.py` | 28 | `from typing import Callable, Iterable` → `collections.abc` (UP035, Q1) |
| Q8 | `core/__init__.py` | ~31 (after `import requests`) | add `__version__ = "1.0.0"` |
| Q8 | `app.py` | 35 | `from typing import Callable` → `collections.abc` (UP035, Q1) |
| Q8 | `app.py` | 41-57 | add `__version__` to `from core import (...)` |
| Q8 | `app.py` | 86-88 | delete `_APP_VERSION` block |
| Q8 | `app.py` | 632 | use `__version__` in `_show_about` |
| Q1 | `app.py` | 1124 | fix E501 (114-char `askyesno` line) |
| Q8 | `cli.py` | 32-44 | add `__version__` to `from core import (...)` |
| Q8 | `cli.py` | 47-100 | add `--version` arg in `_build_parser` |
| Q8 | `tests/test_core.py` | (append) | new `test_core_has_version` |
| Q8 | `tests/test_cli.py` | (append) | new `test_cli_version_flag_exits_0` |
| Q8 | `tests/test_app.py` | ~767-789 | strengthen `test_show_about_displays_version` → assert `core.__version__` |
| Q1 | `requirements-dev.txt` | (append) | add `ruff>=0.6.0` |
| Q1 | `ruff.toml` | NEW | linter config |
| Q1 | `openspec/config.yaml` | 23 | flip `linter` to available |

## Decisions

### D1 (Q1) — ruff configuration and application policy

`ruff.toml` is STANDALONE (no `pyproject.toml` / `setup.cfg` exists; glob-confirmed
in exploration). Config:

```toml
target-version = "py39"
line-length = 100

[lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

Application order: Q2/Q7/Q8 code edits FIRST, then `ruff check .` on the FINAL
state (lints what ships, not an intermediate snapshot). Fix trivial findings
(`ruff check --fix` for SAFE fixes: UP035 import paths, isort); resolve E501 by
reformat; `# noqa: <code>  # <reason>` ONLY for genuinely unavoidable cases.
Update `requirements-dev.txt` (add `ruff>=0.6.0`), install via
`.\venv\Scripts\python.exe -m pip install ruff`, and flip
`openspec/config.yaml:23` to `{ available: true, command: "ruff check ." }`.
**No mypy, no formatter.**

Predicted finding inventory (manual; real count obtained at apply):
- `E501` ×1 — `app.py:1124` (114 chars). Fix by reformatting the f-string/message.
- `UP035` ×2 — `app.py:35`, `core/__init__.py:28` `from typing import Callable[, Iterable]` → `from collections.abc import ...`. SAFE: all uses are annotations and `from __future__ import annotations` makes them strings.
- `F401` — none (re-exports already carry justified `# noqa: F401`).
- `I` — likely clean. `B`/`SIM` — 0–2 low-severity, handled ad hoc.

### D2 (Q2) — FetchError kind validation + mandatory test rewrite

`FetchError.__init__` validates `kind in self.kinds` before any attribute is set.

Before (`core/errors.py:17-20`):
```python
def __init__(self, kind: str, message: str = "", *, status: int | None = None) -> None:
    super().__init__(message or kind)
    self.kind = kind
    self.status = status
```

After:
```python
def __init__(self, kind: str, message: str = "", *, status: int | None = None) -> None:
    if kind not in self.kinds:
        raise ValueError(f"Invalid FetchError kind {kind!r}; must be one of {self.kinds}")
    super().__init__(message or kind)
    self.kind = kind
    self.status = status
```

This BREAKS `tests/test_messages.py:91-103`, which constructs
`FetchError(kind="alien_invasion")` to cover `format_fetch_error`'s
`_GENERIC_FALLBACK`. The rewrite is MANDATORY and bypasses `__init__`:

Before (`tests/test_messages.py:91-94`):
```python
def test_format_fetch_error_unknown_kind_fallback():
    """An unknown kind MUST return a non-empty Spanish fallback (NOT str(exc))."""
    exc = FetchError(kind="alien_invasion", message="raw text")
    out = format_fetch_error(exc)
```

After:
```python
def test_format_fetch_error_unknown_kind_fallback():
    """An unknown kind MUST return a non-empty Spanish fallback (NOT str(exc)).

    Constructs the instance via __new__ to bypass the Q2 kind-validation guard
    in __init__, so the _GENERIC_FALLBACK branch in format_fetch_error stays
    covered (defense-in-depth for kinds added without a matching message key).
    """
    exc = FetchError.__new__(FetchError)
    exc.kind = "alien_invasion"
    exc.status = None
    Exception.__init__(exc, "raw text")
    out = format_fetch_error(exc)
```

The `_GENERIC_FALLBACK` stays in production (defense-in-depth).

### D3 (Q7) — Toplevel-per-test fixture + teardown

`app` fixture builds `SunatTCApp` on a per-test `tk.Toplevel(hidden_root)` and
tears it down. `hidden_root` stays module-scoped (Python 3.14 Windows
`tcl_findLibrary` re-creation bug — single shared root is required). The fixture
becomes a generator (`yield`) to add teardown.

Before (`tests/test_app.py:53-71`):
```python
@pytest.fixture
def app(hidden_root, tmp_cache_dir, monkeypatch):
    """Build a SunatTCApp on a hidden root with safe dialog stubs."""
    import app as app_module
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *a, **k: None)
    ...
    return app_module.SunatTCApp(hidden_root)
```

After:
```python
@pytest.fixture
def app(hidden_root, tmp_cache_dir, monkeypatch):
    """Build a SunatTCApp on a per-test Toplevel with safe dialog stubs."""
    import app as app_module
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *a, **k: None)
    ...
    toplevel = tk.Toplevel(hidden_root)
    application = app_module.SunatTCApp(toplevel)
    yield application
    toplevel.destroy()
```

Compatibility: every `self.root.*` call in `SunatTCApp` (`title`, `geometry`,
`minsize`, `protocol`, `bind_all`, `after`, `update`, `update_idletasks`,
`destroy`) is valid on `tk.Toplevel` (inherits `tk.Wm` + `tk.Misc`). The
production signature `root: tk.Tk` (`app.py:232`) is NOT widened — Q7 is
test-only; `from __future__ import annotations` makes the hint a non-enforcing
string and ruff (no type checker) will not flag a Toplevel passed for `tk.Tk`.

Deliberate NON-migration: `test_geometry_tclerror_falls_back`
(`tests/test_app.py:158-195`) monkeypatches `tk.Tk.geometry` (`:185`); it MUST
stay on `hidden_root` (the patch does not affect `tk.Toplevel`). Cross-test
event draining via `hidden_root.update()` still works (Tk `update()` processes
ALL interpreter events including `Toplevel.after(0, …)`); verify empirically —
top risk.

### D4 (Q8) — centralized `__version__` + `--version` flag

Single source `__version__ = "1.0.0"` in `core/__init__.py` (placed after the
stdlib/third-party imports, before the re-exports block, ~line 31). `app.py`
imports it and uses it in `_show_about`; `cli.py` imports it and adds
`--version`.

`core/__init__.py` (after `import requests`, ~line 31):
```python
__version__ = "1.0.0"
```

`app.py:41-57` — add `__version__` to the `from core import (...)` block.
`app.py:86-88` — DELETE the `_APP_VERSION` block.
`app.py:632` before:
```python
f"Tipo de Cambio SUNAT\nVersión {_APP_VERSION}\n\n"
```
after:
```python
f"Tipo de Cambio SUNAT\nVersión {__version__}\n\n"
```

`cli.py:32-44` — add `__version__` to the `from core import (...)` block.
`cli.py` `_build_parser` — add (e.g. right after the `prog`/`description` setup):
```python
p.add_argument(
    "--version",
    action="version",
    version=f"%(prog)s {__version__}",
)
```
argparse `action="version"` prints to stdout and exits 0 for free; no query mode
is required and the fetch path is never reached. This supersedes the Change F
`_APP_VERSION` spec requirement (see the `app-startup-and-imports` delta).

## TDD Plan (RED test names)

Strict TDD (`config.yaml: strict_tdd: true`). RED tests written BEFORE green code.

- **Q2** (RED): `test_fetch_error_invalid_kind_raises_valueerror` (in
  `tests/test_core.py`) — `with pytest.raises(ValueError): FetchError("bogus")`.
  Also REWRITE (must stay GREEN) `test_format_fetch_error_unknown_kind_fallback`
  via `__new__` (D2).
- **Q7** (no RED): the 80 existing tests are the GREEN proof. Run `pytest -q`
  immediately after the fixture edit.
- **Q8** (RED, 3 tests): `test_core_has_version`
  (`assert core.__version__ == "1.0.0"`); `test_cli_version_flag_exits_0`
  (`cli.run(["--version"])` → `SystemExit(0)`, captured stdout contains
  `"1.0.0"`); strengthen `test_show_about_displays_version` to assert
  `core.__version__ in message` (not the literal `"1.0.0"`).
- **Q1** (no RED): gate is `ruff check .` clean.

## Apply Order

**Q2 → Q7 → Q8 → Q1 (lint final).** Q1 runs LAST so it lints the final state
after all behavior/test edits; otherwise later edits re-introduce findings.

## PR Split

Single PR, ~120 LoC. No chained PRs (well under the 400-line review budget).

## Rollback

`git revert` of the change commit(s). Layer isolation per item (Q2 in
`core/errors.py` + test rewrite; Q7 in `tests/test_app.py` fixture; Q8 in
`core/__init__.py`/`app.py`/`cli.py`; Q1 tooling). No data migrations; cache and
state unchanged.

## Out of Scope

mypy / type-checker; black/blue formatter; any Change A–F item; widening the
`root: tk.Tk` production signature; validating `status` ranges against `kind`;
reading version from package metadata.
