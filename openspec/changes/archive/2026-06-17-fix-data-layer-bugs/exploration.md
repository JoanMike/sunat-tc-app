# Exploration: fix-data-layer-bugs

Change scope: 8 real bugs / quality items in the data layer + CLI/GUI error
surfacing + constants deduplication. Strict TDD is on; implementation will be
RED-first (red-green-refactor) per `openspec/config.yaml:9` (`strict_tdd: true`)
and the `apply.tdd: true` rule.

## Verification of line numbers

All eight items' referenced lines are still accurate against the current tree.
Two minor cosmetic drifts:

- B9 call sites: prompt said `app.py:97,319-325,658`. Actual: `app.py:96`
  (`min_year` default arg, not `MAX_YEAR`); `app.py:319-320` (`year_spin`
  bounds); `app.py:658-659` (validation + error message). `app.py:97` is the
  `max_year: int | None = None` parameter — it falls back to
  `date.today().year` at construction, so it does NOT consume `MAX_YEAR`.
  Effective MAX_YEAR blast radius = **3 lines (320, 658, 659)** + 1 import line.
- `MAX_YEAR` is NOT used anywhere in `cli.py`. The CLI's `--month` validation
  goes through `validate_month` (`core/validators.py`), which already uses
  `_max_year()` dynamically. Only `app.py` directly imports `MAX_YEAR`.

| Item | Provided line(s) | Actual line(s) | Match |
| --- | --- | --- | --- |
| B1 `_get_with_retry` | `core/__init__.py:122-161` | 122-161 | OK |
| B1 `RETRYABLE_STATUS` | `core/__init__.py:48` | 48 | OK |
| B1 `rate_limit` declared | `core/errors.py:15` | 15 | OK |
| B1 mapped message | `cli.py:192` | 192 | OK |
| B1 spec reserve | `data-fetch/spec.md:23` | 23 | OK |
| B2 `_save_xlsx` `strptime` | `cli.py:159` | 159 | OK |
| B2 outer `except OSError` | `cli.py:296` | 296 | OK |
| B2 app.py defend pattern | `app.py:916-919` | 916-919 | OK |
| B3 GUI worker `on_done([], f"Error inesperado: {exc}")` | `app.py:747-748` | 747-748 | OK |
| B3 `_format_fetch_error` + dict | `cli.py:184-210` | 184-210 | OK |
| B3 CLI call site | `cli.py:276` | 276 | OK |
| B4 `load_state` | `core/__init__.py:423-436` | 423-436 | OK |
| B4 `merged.update(data)` | `:430` | 430 | OK |
| B4 `except (...)` | `:435` | 435 | OK |
| B8 `MIN_YEAR` dup | `core/__init__.py:47` + `core/validators.py:15` | 47, 15 | OK (two sources of truth) |
| B9 `MAX_YEAR` module const | `core/__init__.py:46` | 46 | OK |
| B9 `_max_year()` dynamic | `core/validators.py:20-22` | 20-22 | OK |
| Q5 dead branch | `core/__init__.py:360-361` | 360-361 | OK (validate_range already raises) |

## Current State

The data layer (`core/`) raises `FetchError(kind=...)` for fetch failures,
but the actual `kind` values used at runtime are only
`{"network","http_4xx","http_5xx","parse","input"}` — `rate_limit` is
declared in `core/errors.py:15` and reserved by the data-fetch spec, but
never raised. When the API throttles (HTTP 429), 429 is currently in
`RETRYABLE_STATUS` and after exhausting retries the code raises
`FetchError(kind="http_5xx", status=429)`, which the CLI maps to
"El servicio de SUNAT no está disponible (HTTP 429)…" — semantically
wrong; the user sees "server down" instead of "rate-limited, wait a moment."

Error message formatting lives in `cli.py:184-210` (`_format_fetch_error` +
`_FETCH_ERROR_MESSAGES_ES`), but the GUI worker at `app.py:747-748` does
`except Exception as exc: on_done([], f"Error inesperado: {exc}")` and
formats with raw `str(exc)`. For a `FetchError`, `str(exc)` is the
`message` argument (English-y technical text like "HTTP 503"), so Spanish
GUI users see English debug output.

CLI XLSX export assumes row dicts have valid ISO `fecha` strings. The GUI
defends this at `app.py:916-919`; the CLI does not. A cache row with a
malformed `fecha` (theoretically possible after manual DB edits or a future
API change) crashes with `ValueError` that escapes the `except OSError`
block at `cli.py:296` → unhandled traceback → exit 1 (should be exit 5 per
README contract).

`core/load_state` validates the *JSON syntax* of `state.json` but not the
*JSON shape*. `json.load` happily reads `5`, `[1,2,3]`, or `null`; the
subsequent `dict.update(data)` then raises `TypeError` that escapes the
`except (OSError, json.JSONDecodeError, ValueError)` tuple.

`MIN_YEAR = 2000` is defined in BOTH `core/__init__.py:47` AND
`core/validators.py:15`. Two sources of truth — drift waiting to happen.

`MAX_YEAR = date.today().year` is a module-level expression evaluated ONCE
at import time. If the process stays open across midnight on Dec 31, the
constant is stale while `core/validators.py:_max_year()` (re-evaluated on
every call) is fresh. The inconsistency is observable as: GUI spinbox upper
bound (`app.py:320`) and CLI `--month` validator disagree across a New
Year's boundary.

`fetch_range` has a dead `if end < start: return []` at `:360-361`; the
preceding `validate_range(start, end)` at `:356-358` already raises
`FetchError(kind="input")` for `start > end`, so the post-validate branch
is unreachable.

## Affected Areas

- `core/__init__.py` — `_get_with_retry` (B1), `_get_with_retry` data
  import path, `MAX_YEAR` / `MIN_YEAR` module constants (B8/B9), `load_state`
  (B4), `fetch_range` dead branch (Q5).
- `core/validators.py` — `MIN_YEAR` definition dedup (B8).
- `core/messages.py` (NEW) — destination for `_format_fetch_error` + dict
  (Q4). New module, public API `format_fetch_error(exc) -> str`.
- `cli.py` — `_format_fetch_error`/`_FETCH_ERROR_MESSAGES_ES` removed,
  imported from `core.messages`; `_save_xlsx` `strptime` guarded (B2);
  outer `except OSError` widened (B2).
- `app.py` — `_fetch_worker` exception handler (B3), `MIN_YEAR`/`MAX_YEAR`
  call sites updated (B8/B9), `from core.messages import format_fetch_error`
  added.
- `tests/` — new RED-first tests for each item (apply phase).

### Blast radius — `MIN_YEAR`

7 Python reference sites across 3 source files + 2 docstring/comment
references in tests:

| File | Line | Form |
| --- | --- | --- |
| `core/__init__.py` | 47 | `MIN_YEAR = 2000` (definition — to be removed) |
| `core/validators.py` | 15 | `MIN_YEAR = 2000` (definition — becomes canonical) |
| `app.py` | 42 | `MIN_YEAR,` (re-export import) |
| `app.py` | 96 | `min_year: int = MIN_YEAR` (DateEntry default arg) |
| `app.py` | 319 | `from_=MIN_YEAR` (year_spin lower bound) |
| `app.py` | 658 | `MIN_YEAR <= yr <= MAX_YEAR` (validation) |
| `app.py` | 659 | f-string `{MIN_YEAR}` (error msg) |
| `tests/test_core.py` | 156 | `# year below MIN_YEAR` (comment) |
| `tests/test_cli.py` | 69 | `--month` with a year below MIN_YEAR (docstring) |

Note: `openspec/specs/input-validation/spec.md` references `MIN_YEAR` as
a spec-level identifier in 4 places — these are documentation tokens, not
Python identifiers; they do not require import rewrites.

### Blast radius — `MAX_YEAR`

3 Python reference sites + 1 import line, all in `app.py`:

| File | Line | Form | Dynamism needed |
| --- | --- | --- | --- |
| `core/__init__.py` | 46 | `MAX_YEAR = date.today().year` (definition) | n/a |
| `app.py` | 43 | `MAX_YEAR,` (import) | n/a |
| `app.py` | 320 | `to=MAX_YEAR` (year_spin upper bound) | low — GUI is rebuilt on each launch |
| `app.py` | 658 | `yr <= MAX_YEAR` (validation in `_validate_inputs`) | HIGH — must be fresh |
| `app.py` | 659 | `{MAX_YEAR}` in error msg | inherits dynamism from L658 |

No references in `cli.py`, `core/validators.py`, or any test file.

### Blast radius — Q4 (`_format_fetch_error` / `_FETCH_ERROR_MESSAGES_ES`)

Confirmed by grep: ZERO references outside `cli.py`. The dict is defined
once at `cli.py:187` and read once at `cli.py:204` (inside the same
function `_format_fetch_error`). The function is defined at `cli.py:197`
and called at exactly one site: `cli.py:276`. After the move:

- `core/messages.py` — new file; `format_fetch_error(exc: FetchError) -> str`
  + module-level `_FETCH_ERROR_MESSAGES_ES` dict.
- `cli.py:276` — change `_format_fetch_error(exc)` →
  `format_fetch_error(exc)` (imported from `core.messages`).
- `app.py:_fetch_worker` (`app.py:747-748`) — add `FetchError` branch using
  the shared formatter; keep generic branch for non-`FetchError`.

## Approaches

### B1 — Raise `kind="rate_limit"` on 429

1. **Branch inside `RETRYABLE_STATUS` check** (preferred): keep 429 in
   `RETRYABLE_STATUS` (still transient, still retryable), but on the
   exhaustion branch check `r.status_code == 429` first and raise
   `FetchError(kind="rate_limit", ...)`; fall through to
   `kind="http_5xx"` for the rest.
   - Pros: minimal diff; preserves retry behavior; matches spec
     (`data-fetch.md:23` reserves `rate_limit` for API throttling).
   - Cons: special-cases one status inside the generic block.
   - Effort: Low.

2. **Separate 429 from `RETRYABLE_STATUS`, treat as non-retryable**:
   remove 429 from the set, raise `rate_limit` on first occurrence.
   - Pros: cleanest; matches user intent of "you asked too fast, back off".
   - Cons: violates retry contract; one-shot failure instead of
     exponential backoff. Worse UX for transient spikes.
   - Effort: Low.

3. **Retry-on-429 then 429-distinct-raise** (option 1 spelled out): same as
   option 1; document explicitly that 429 stays retryable per design.
   - Same as option 1; just explicit on the rationale.

### B2 — CLI XLSX malformed-fecha guard

1. **Inner try/except + widen outer `except`** (mirrors GUI): in
   `_save_xlsx`, wrap the per-row `strptime` with try/except falling back
   to the raw string (parity with `app.py:916-919`); AND widen the
   output-path `except OSError` at `cli.py:296` to `except (OSError,
   ValueError, TypeError)` so any other unexpected write-path exception
   still routes to exit 5 instead of crashing.
   - Pros: matches GUI behavior; belt-and-suspenders for any future
     malformed data; preserves exit-5 contract per README.
   - Cons: `ValueError` is broad; could mask real bugs.
   - Effort: Low.

2. **Restructure to `_safe_strptime_fecha(row)` helper in `core`**:
   extract the parse-or-fallback logic into a shared helper, used by both
   `_save_xlsx` and `_export_excel`. Cleaner long-term but expands
   blast radius beyond this change.
   - Pros: deduplicates parse logic across GUI/CLI.
   - Cons: scope creep; not strictly necessary for the bug fix.
   - Effort: Medium. Defer to a future quality change.

### B3 + Q4 — Shared `format_fetch_error` in `core/messages.py`

1. **New module `core/messages.py`, keep `_format_fetch_error` CLI wrapper**
   (preferred): move `_FETCH_ERROR_MESSAGES_ES` (dict) and
   `format_fetch_error(exc)` (public, un-prefixed) into
   `core/messages.py`. Re-export from `core/__init__.py` so
   `from core import format_fetch_error` works. `cli.py:276` calls
   `core.format_fetch_error(exc)` directly (drop the local wrapper — it
   was a thin shim). `app.py:_fetch_worker` gets a
   `except FetchError as exc: on_done([], format_fetch_error(exc))` branch
   BEFORE the generic `except Exception`, with the generic branch kept
   as the safety net for non-`FetchError` exceptions (changing its text
   to "Error inesperado: {exc}" stays as English debug fallback — actually
   "Error inesperado al consultar el tipo de cambio." is more Spanish,
   but "Error inesperado: {exc}" is the existing string and matches the
   prompt's "keep generic" guidance).
   - Pros: single source of truth for error → message mapping; matches
     data-fetch spec's promise that CLI/GUI consume the layer "the same
     way"; minimal CLI churn (one import line + one call site).
   - Cons: introduces a new module.
   - Effort: Low.

2. **Inline the dict into both `cli.py` and `app.py`**: copy the dict
   into both files, format locally.
   - Pros: no new module.
   - Cons: violates DRY; the very thing Q4 was created to fix.
   - Effort: Low but wrong.

### B4 — `load_state` non-dict guard

1. **`if not isinstance(data, dict): return dict(DEFAULT_STATE)` BEFORE
   the merge + add `TypeError` to the except tuple** (both fixes; belt-
   and-suspenders as the prompt suggests).
   - Pros: explicit shape check (the intent) + defensive except (catches
     any future `dict.update` variant that raises `TypeError`).
   - Cons: none material.
   - Effort: Low.

2. **Just add `TypeError` to the except tuple**: catches the immediate
   failure but leaves the shape check implicit.
   - Pros: smaller diff.
   - Cons: less explicit; future reader has to know `dict.update`
     raises on non-dict input.
   - Effort: Low.

### B8 — `MIN_YEAR` single source of truth

1. **Delete `core/__init__.py:47`, import from `.validators`, keep public
   re-export** (preferred):
   ```python
   # core/__init__.py
   from .validators import MIN_YEAR, validate_month, validate_range  # noqa: F401
   ```
   `from core import MIN_YEAR` keeps working unchanged. `app.py:42`
   import line untouched.
   - Pros: zero downstream changes; canonical home for the constant
     stays near the validators that use it.
   - Cons: introduces an import-order dependency from `core.__init__` to
     `core.validators` (currently none — `validators` is imported by
     `__init__` already at line 38, so no new ordering issue).
   - Effort: Low.

### B9 — Dynamic `max_year()`

1. **`max_year()` function in `core`, update `app.py` call sites** (preferred):
   ```python
   # core/__init__.py
   from .validators import _max_year  # noqa: F401  (private re-export)
   def max_year() -> int: return date.today().year
   ```
   Then in `app.py`:
   - Line 43: drop `MAX_YEAR` from the import block.
   - Line 320: `to=max_year()` — fresh value at GUI build time. Same
     staleness window as today (one import) but recomputed on each
     invocation of `_build_ui`, which is fine (called once at startup).
     Actually `max_year()` at L320 still resolves at GUI-build time
     (fine).
   - Line 658: `yr <= max_year()` — fresh on every `_validate_inputs`
     call. **This is the key win.**
   - Line 659: `{max_year()}` in error msg — fresh.
   - Pros: explicit dynamism; matches `validators._max_year()` pattern;
     fixes the New Year's Eve staleness.
   - Cons: 3 call-site edits; one import-line edit. Breaking change for
     any external `from core import MAX_YEAR` consumer (none in this
     repo, none in tests).
   - Effort: Low.

2. **Deprecation alias `MAX_YEAR = max_year()` + warning**: keep
   `MAX_YEAR` as a module-level expression `MAX_YEAR = max_year()` for
   backward compat. Reads as an alias but is still evaluated at import
   time — DOES NOT fix the staleness bug.
   - Pros: zero call-site churn.
   - Cons: doesn't fix the bug; the whole point is dynamism. **Wrong
     for this change.**
   - Effort: Low (but useless).

3. **Property on a module-level class**: not idiomatic for this flat
   module; rejected.

### Q5 — Dead branch in `fetch_range`

1. **Delete the `if end < start: return []` block at `:360-361`** (the
   only option). Replace with a comment noting that `validate_range` is
   the single guard.
   - Pros: removes unreachable code; clarifies contract.
   - Cons: none.
   - Effort: Trivial.

## Recommendation

Apply each item's preferred approach above. Specifically:

- **B1**: option 1 — keep 429 in `RETRYABLE_STATUS`, raise `kind="rate_limit"`
  on exhaustion. Document in the data-fetch spec scenario.
- **B2**: option 1 — inner try/except mirroring GUI + widen outer
  `except OSError` to `except (OSError, ValueError, TypeError)`.
- **B3 + Q4**: option 1 — new `core/messages.py` with `format_fetch_error`
  + dict, re-exported from `core`. `app._fetch_worker` adds a
  `FetchError`-specific branch; generic `except Exception` stays as-is.
- **B4**: option 1 — explicit `isinstance(data, dict)` check + add
  `TypeError` to the except tuple.
- **B8**: option 1 — single canonical `MIN_YEAR` in `validators.py`,
  re-exported from `core`.
- **B9**: option 1 — `max_year()` function in `core`, update 3 lines in
  `app.py` (320, 658, 659) plus the import on L43. No backward-compat
  alias; this is an internal repo, no external consumers.
- **Q5**: option 1 — delete the dead branch.

All RED-first tests: new tests live in `tests/test_core.py` for B1/B4/B8/B9
core behavior, `tests/test_cli.py` for B2 + Q4 call-site integration, and
`tests/test_app.py` for B3 GUI worker integration.

## Risks

- **B9 breaking change**: removing `core.MAX_YEAR` breaks any future
  `from core import MAX_YEAR`. Confirmed: only `app.py:43` does this in
  the whole repo. Low risk; update `app.py` in the same change.
- **B2 widened except**: catching `ValueError`/`TypeError` in the output
  block could mask bugs (e.g. an `int()` conversion failure silently
  becomes exit 5 instead of a traceback). Mitigation: narrow the wrap to
  only the `_save_xlsx` / `_save_csv` calls (already the case — the
  `try:` block at `cli.py:284` only wraps output writes).
- **B4 widening except + adding `TypeError`**: the explicit
  `isinstance(data, dict)` check is the primary fix; the `TypeError` in
  the except tuple is a safety net for any future bug where the shape
  check is bypassed.
- **Q4 module split**: new module means new test surface, but the move
  is mechanical (copy + rename). Risk: forgetting to remove the old
  `cli.py` definitions would leave dead code. Mitigation: delete the
  `_FETCH_ERROR_MESSAGES_ES` and `_format_fetch_error` from `cli.py` in
  the same commit.
- **B1 spec drift**: `openspec/specs/data-fetch/spec.md:27-30` currently
  has a scenario for `kind="http_5xx"` after retries. A new scenario for
  429 → `rate_limit` must be added in the spec phase (not this phase).
  Flagging for the spec author.

## Ready for Proposal

Yes. All 8 items verified, blast radius mapped, design choices documented.
The orchestrator can hand this to `sdd-propose` with `change-name =
fix-data-layer-bugs`. Recommended PR grouping (within `review_budget: 400`):

- PR 1 (Data layer, ~120 LoC): B1, B4, B8, B9, Q5 + their core tests.
- PR 2 (Surface integration, ~100 LoC): B2, B3, Q4 + CLI/GUI tests.

Both fit comfortably under the 400-line review budget. Sequential, not
stacked (B3 needs `core.messages` from PR 1... actually Q4/B3 only needs
the new module which can land in PR 2; PR 1 doesn't depend on it). They
can be sequential or one PR if the total stays under 400. Total LoC ≈ 220
as predicted.
