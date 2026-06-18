# Tasks: fix-data-layer-bugs

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~220 (PR1 ~120, PR2 ~100) |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR1 data layer → PR2 surface integration |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Data-layer fixes (B1, B4, B8, B9, Q5) + tests 1–7 | PR 1 | Base: `main`; ~120 LoC; independent of PR2 |
| 2 | Surface integration (B2, B3, Q4) + `core/messages.py` + tests 8–15 | PR 2 | Base: PR1 branch OR `main` post-merge; ~100 LoC |

## Phase 1: PR1 — Data layer (RED-first)

- [x] 1.1 **RED** — `tests/test_core.py`: add `test_get_with_retry_429_exhausted_raises_rate_limit` and `test_get_with_retry_5xx_exhausted_still_raises_http_5xx`. `pytest -q` → RED.
- [x] 1.2 **GREEN** — `core/__init__.py` `_get_with_retry` (~L139-148): keep 429 in `RETRYABLE_STATUS`; on exhaustion, raise `FetchError(kind="rate_limit")` if last status == 429 else `kind="http_5xx"`. `pytest -q` → GREEN.
- [x] 1.3 **RED** — `tests/test_core.py`: add `test_load_state_returns_default_when_state_is_list` and `test_load_state_returns_default_when_state_is_null`. `pytest -q` → RED.
- [x] 1.4 **GREEN** — `core/__init__.py` `load_state` (~L423-436): add `isinstance(data, dict)` guard returning `dict(DEFAULT_STATE)`; add `TypeError` to except. `pytest -q` → GREEN.
- [x] 1.5 **REFACTOR (B8)** — `core/__init__.py` L38 + L46-47: delete `MIN_YEAR = 2000`; re-export from `.validators`. Add `tests/test_core.py::test_min_year_exported_from_validators`.
- [x] 1.6 **RED** — `tests/test_core.py`: add `test_max_year_returns_today_year`. `pytest -q` → RED.
- [x] 1.7 **GREEN** — `core/__init__.py`: replace `MAX_YEAR` with `def max_year() -> int: return date.today().year`. `app.py` L43 (drop import), L320 (`to=max_year()`), L658 (`yr <= max_year()`), L659 (f-string `{max_year()}`). Add `tests/test_app.py::test_app_imports_min_year_from_core` and `test_app_validates_against_dynamic_max_year` (mock today to year+1). `pytest -q` → GREEN.
- [x] 1.8 **REFACTOR (Q5)** — `core/__init__.py` L360-361: delete dead `if end < start: return []`. `test_fetch_range_rejects_inverted_range` still passes.
- [x] 1.9 **VERIFY** — `pytest -q`; tests 1–7 GREEN, full suite green. Commits: one per RED+GREEN pair; T1.7 bundles core + `app.py`.

## Phase 2: PR2 — Surface integration (RED-first)

- [x] 2.1 **RED** — new `tests/test_messages.py`: add `test_format_fetch_error_maps_all_kinds` and `test_format_fetch_error_substitutes_http_status`. `pytest -q` → RED (module missing).
- [x] 2.2 **GREEN** — create `core/messages.py` with `_FETCH_ERROR_MESSAGES_ES` + `format_fetch_error(exc: FetchError) -> str`. Re-export from `core/__init__.py`. `pytest -q` → GREEN.
- [x] 2.3 **REFACTOR** — `cli.py` L32-43: delete `_FETCH_ERROR_MESSAGES_ES` + `_format_fetch_error`; swap `cli.py:276` to `format_fetch_error(exc)`. Add `tests/test_cli.py::test_cli_routes_fetch_error_through_core_messages`.
- [x] 2.4 **RED** — `tests/test_cli.py`: add `test_save_xlsx_skips_row_with_malformed_fecha` and `test_save_xlsx_exits_5_on_unexpected_write_error`. `pytest -q` → RED.
- [x] 2.5 **GREEN** — `cli.py` `_save_xlsx` (~L184-210): wrap per-row `datetime.strptime` in `try/except ValueError` (`app.py:916-919` pattern). Widen `cli.py:284-298` `except OSError` → `except (OSError, ValueError, TypeError)`. `pytest -q` → GREEN.
- [x] 2.6 **RED** — `tests/test_app.py`: add `test_fetch_worker_renders_spanish_message_on_fetch_error`. `pytest -q` → RED.
- [x] 2.7 **GREEN** — `app.py` `_fetch_worker` (~L744-749): insert `except FetchError as exc: on_done([], format_fetch_error(exc))` between `except _Cancelled` and `except Exception`. Add `FetchError` + `format_fetch_error` imports L40-53. `pytest -q` → GREEN.
- [x] 2.8 **VERIFY** — `pytest -q`; tests 8–15 GREEN, full suite green. Commits: 2.2+2.3 bundle (Q4); 2.5 and 2.7 independent.
