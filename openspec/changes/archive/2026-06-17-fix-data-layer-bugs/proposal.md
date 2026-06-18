# Proposal: fix-data-layer-bugs

## Intent

The data layer (`core/`) and its CLI/GUI consumers have eight small but real defects that surface as wrong user-facing messages, unhandled tracebacks, and silent contract drift. HTTP 429 is misclassified as a server outage; the GUI worker shows raw English exception text from `str(exc)`; the CLI XLSX export crashes with an unhandled `ValueError` on a malformed `fecha`; `load_state` accepts a non-dict JSON payload and dies on `dict.update`; `MIN_YEAR` is defined twice and `MAX_YEAR` is a static module constant that goes stale across midnight on Dec 31; and `fetch_range` carries an unreachable defensive branch. The fix is mechanical, fully covered by the existing pytest harness, and constrained to ~220 LoC.

## Scope

### In Scope (8 items, ~220 LoC, 2 sequential PRs)

- **B1** — `core/_get_with_retry`: keep 429 in `RETRYABLE_STATUS`; on retry exhaustion, raise `FetchError(kind="rate_limit")` instead of `kind="http_5xx"`.
- **B2** — `cli._save_xlsx`: guard per-row `datetime.strptime` with try/except (mirror `app.py:916-919`), falling back to the raw `fecha` string on `ValueError` (exit 0, row preserved); widen the output-block `except OSError` at `cli.py:296` to `except (OSError, ValueError, TypeError)` so genuinely unexpected write errors → exit 5, not unhandled traceback exit 1.
- **B3 + Q4** — New `core/messages.py` with `format_fetch_error(exc: FetchError) -> str` and `_FETCH_ERROR_MESSAGES_ES`. Re-exported from `core`. `cli.py:276` calls it; `app._fetch_worker` adds `except FetchError as exc: on_done([], format_fetch_error(exc))` BEFORE the generic `except Exception`.
- **B4** — `core.load_state`: explicit `isinstance(data, dict)` guard returning `dict(DEFAULT_STATE)`; add `TypeError` to the except tuple at `:435`.
- **B8** — Delete `core/__init__.py:47 MIN_YEAR = 2000`; re-export `MIN_YEAR` from `.validators` (single source). `from core import MIN_YEAR` keeps working unchanged.
- **B9** — Replace `core.MAX_YEAR = date.today().year` with `def max_year() -> int: return date.today().year`. Update `app.py` L43 (drop from import), L320 (`to=max_year()`), L658 (`yr <= max_year()`), L659 (`{max_year()}` in error msg). No backward-compat alias (zero in-repo consumers confirmed).
- **Q5** — Delete dead `if end < start: return []` branch at `core/__init__.py:360-361` (preceding `validate_range` already raises `FetchError(kind="input")`).

### Out of Scope

- **Change B**: items B5, B6, B7 (deferred).
- **Change D**: items D1-D5 (deferred).
- **Change E**: items P1-P4 (deferred).
- **Change F**: items G1-G10 (deferred).
- **Change G**: items Q1, Q2, Q7, Q8 (deferred).

## Capabilities

### New Capabilities
None. The new `core/messages.py` module is an implementation detail of the `data-fetch` error-surfacing contract, not a new user-facing capability.

### Modified Capabilities

- `data-fetch` — add a scenario: 429 retry-exhaustion → `kind="rate_limit"` (status `429`); tighten narrative on the `kind` enumeration to reflect that `rate_limit` is now actively raised, not just reserved.
- `input-validation` — narrative update: `MAX_YEAR` (module constant) is replaced by `max_year()` (callable) in `core`; `MIN_YEAR` is canonically defined in `validators.py` and re-exported from `core` (one source of truth).
- `gui-worker-lifecycle` — `_fetch_worker` MUST branch on `FetchError` before the generic `except Exception` and route to `on_done([], format_fetch_error(exc))` so the GUI surfaces the Spanish message from `core.messages`, not raw `str(exc)`.
- `localization` — Spanish mapping for `FetchError.kind` values lives in `core.messages` and is shared by CLI and GUI; the GUI MUST NOT fall back to raw `str(exc)` for `FetchError`.

## Approach

Two sequential PRs, both well under `review_budget: 400` (per `config.yaml:48`):

- **PR 1 — Data layer** (~120 LoC): B1, B4, B8, B9, Q5 + `tests/test_core.py` cases. Pure core module + its tests; no surface (CLI/GUI) changes; spec scenarios added by `sdd-spec` for B1.
- **PR 2 — Surface integration** (~100 LoC): B2, B3, Q4. New `core/messages.py`; `cli.py` drops its private `_format_fetch_error` and calls `core.format_fetch_error`; `app._fetch_worker` adds the `FetchError` branch; `tests/test_cli.py` and `tests/test_app.py` cases. PR 2 does not strictly depend on PR 1; either order is safe, and they could even ship as a single ~220 LoC PR.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `core/__init__.py` | Modified | B1 retry/raise branch, B4 guard, B8 import re-export, B9 `max_year()` function, Q5 dead-branch delete |
| `core/validators.py` | Canonical source | B8 `MIN_YEAR` becomes the single definition |
| `core/messages.py` | New | Q4 `format_fetch_error` + `_FETCH_ERROR_MESSAGES_ES` |
| `cli.py` | Modified | B2 inner try/except + widened outer except; B3/Q4 import + call-site swap at `:276` |
| `app.py` | Modified | B3 `FetchError` branch in `_fetch_worker`; B8/B9 import + 3 call-site edits (L320, L658, L659) |
| `tests/test_core.py` | Modified | B1, B4, B8, B9, Q5 RED-first cases |
| `tests/test_cli.py` | Modified | B2 + Q4 CLI integration cases |
| `tests/test_app.py` | Modified | B3 `_fetch_worker` FetchError-branch case |
| `tests/test_messages.py` | New (small) | Direct unit tests for `format_fetch_error` mapping |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| B9 breaks `from core import MAX_YEAR` for any external consumer | Low | Confirmed zero in-repo consumers via grep; no external SDK ships; update `app.py` in the same commit |
| B2 widened `except (OSError, ValueError, TypeError)` masks unrelated bugs | Low | The `try` block at `cli.py:284` wraps only output writes; narrow scope preserved by structure |
| Q4 module split leaves dead CLI definitions | Low | Delete `_format_fetch_error` and `_FETCH_ERROR_MESSAGES_ES` from `cli.py` in the same commit as the new module; RED-first test asserts the new import path |
| B1 spec drift on `data-fetch` `kind` enumeration | Low | `sdd-spec` adds the 429 scenario before implementation lands; flag carried forward in this proposal |
| One call site of `MAX_YEAR`/`max_year()` is missed in `app.py` | Low | RED-first test in `tests/test_app.py` covers `_validate_inputs` with year > today |

## Rollback Plan

`git revert <sha>` of PR 1 and/or PR 2. No data migration, no schema change, no cache layout change, no on-disk format change. State files and SQLite cache remain bit-identical. The only persistent side effect is `core.MAX_YEAR` removal in PR 1; revert restores the constant and the `app.py` import block in a single commit. Test suite returns to pre-change green.

## Dependencies

None new. Pytest harness already bootstrapped (`config.yaml:9 strict_tdd: true`; `apply.test_command: "pytest -q"`). No package additions, no schema migrations.

## Strict TDD — RED-first test names

Per `config.yaml:45 apply.tdd: true`, every item writes its failing test FIRST, runs `pytest -q` to confirm RED, then implements, then re-runs to confirm GREEN.

- **B1** — `tests/test_core.py::test_get_with_retry_429_exhausted_raises_rate_limit`
- **B2** — `tests/test_cli.py::test_save_xlsx_skips_row_with_malformed_fecha`; `test_save_xlsx_exits_5_on_unexpected_write_error`
- **B3** — `tests/test_app.py::test_fetch_worker_renders_spanish_message_on_fetch_error`
- **B4** — `tests/test_core.py::test_load_state_returns_default_when_state_is_list`; `test_load_state_returns_default_when_state_is_null`
- **B8** — `tests/test_core.py::test_min_year_exported_from_validators`; `tests/test_app.py::test_app_imports_min_year_from_core`
- **B9** — `tests/test_core.py::test_max_year_returns_today_year`; `tests/test_app.py::test_app_validates_against_dynamic_max_year`
- **Q4** — `tests/test_messages.py::test_format_fetch_error_maps_all_kinds`; `tests/test_cli.py::test_cli_routes_fetch_error_through_core_messages`
- **Q5** — `tests/test_core.py::test_fetch_range_rejects_inverted_range` (already exists, asserts current behavior; passes unchanged after the dead-branch delete)

## Success Criteria

- [ ] `pytest -q` passes 100% green, including all new RED-first cases.
- [ ] `grep -n 'MAX_YEAR' core/ app.py` returns zero matches.
- [ ] `grep -n 'MIN_YEAR = 2000' core/` returns exactly one match in `validators.py`.
- [ ] `grep -n _format_fetch_error cli.py` returns zero matches.
- [ ] On a 429 burst that exhausts retries, CLI prints a Spanish rate-limit message (not the SUNAT 5xx text).
- [ ] GUI `_fetch_worker` `on_done` shows a Spanish fetch-error message on `FetchError`, not raw `str(exc)`.
- [ ] CLI `--xlsx` on a cache row with malformed `fecha` exits 5, not traceback exit 1.
- [ ] `data-fetch` and `input-validation` specs updated with the new scenario / narrative before `sdd-apply`.
