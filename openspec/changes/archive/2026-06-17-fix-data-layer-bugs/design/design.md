# Design: fix-data-layer-bugs

## Goal

Resolve eight data-layer and surface defects (B1, B2, B3, B4, B8, B9, Q4, Q5) in two sequential PRs (≤220 LoC, ≤400 review budget each). Specs lock the WHAT; this locks the HOW.

## Files

| File | Lines | Change |
|---|---|---|
| `core/__init__.py` | 38, 46–47, 139–148, 360–361, 423–436 | Re-export `MIN_YEAR` from `validators` and `format_fetch_error` from `messages`; replace `MAX_YEAR` const with `def max_year(): return date.today().year`; delete `MIN_YEAR = 2000` dup; flip `kind` to `"rate_limit"` for 429 in `_get_with_retry` exhaustion; delete dead `if end < start: return []`; add `isinstance(data, dict)` guard + `TypeError` to `load_state` except |
| `core/validators.py` | — | Unchanged (`MIN_YEAR` already canonical) |
| `core/messages.py` | New (~30 LoC) | Public `format_fetch_error(exc)` + private `_FETCH_ERROR_MESSAGES_ES` dict |
| `cli.py` | 32–43, 158–160, 184–210, 276, 284–298 | Drop local `_FETCH_ERROR_MESSAGES_ES` + `_format_fetch_error`; import `format_fetch_error` from `core`; per-row `strptime` `try/except ValueError`; widen output `except OSError` → `except (OSError, ValueError, TypeError)` |
| `app.py` | 40–53, 320, 658–659, 744–749 | Drop `MAX_YEAR` from import; add `FetchError` + `format_fetch_error` imports; `to=max_year()` (L320); `yr <= max_year()` + f-string `{max_year()}` (L658–659); insert `except FetchError` branch between `except _Cancelled` and `except Exception` |
| `tests/test_core.py` | append | B1, B4, B8, B9, Q5 |
| `tests/test_cli.py` | append | B2, Q4 call-site |
| `tests/test_app.py` | append | B3, B8, B9 GUI |
| `tests/test_messages.py` | New | Unit tests for `format_fetch_error` |

## Architecture Decisions

| ID | Decision | Rationale |
|---|---|---|
| **D1** | 429 stays in `RETRYABLE_STATUS`; exhaustion flips `kind` to `"rate_limit"` via one `if r.status_code == 429` INSIDE the existing exhaustion block. | Preserves exponential backoff; minimal diff; matches the data-fetch spec reserve. |
| **D2** | New `core/messages.py` (one public `format_fetch_error` + private dict), re-exported from `core/__init__.py`. | Single source of truth; keeps surface → core one-way. |
| **D3** | `max_year()` is a function in `core`; NO `MAX_YEAR` deprecation alias. | A static alias still evaluates at import — would NOT fix the New Year's Eve staleness. Zero in-repo consumers beyond `app.py:43`; break is contained. |
| **D4** | `MIN_YEAR` canonical in `core/validators.py` (already there); re-export from `core/__init__.py:38`. `app.py:42` import line untouched. | `validators.py` is the natural home — `validate_month` already uses it. Moving to `__init__.py` would invert the parent/child import direction. |
| **D5** | `load_state` gets BOTH `isinstance(data, dict)` guard (returns `dict(DEFAULT_STATE)`) AND `TypeError` added to the except tuple. | Belt-and-suspenders: explicit shape check + safety net for any future merge-site failure. Matches `core._normalize_item`'s pattern. |
| **D6** | Output `try` at `cli.py:284` widens `except OSError` → `except (OSError, ValueError, TypeError)`. `try` wraps ONLY output writes (L285–294); parser errors at L246–272 still raise normally. Inner `_save_xlsx` per-row `strptime` gets its own `try/except ValueError` mirroring `app.py:916–919`. | Inner guard mirrors GUI parity; outer widening is bounded by the existing `try` block structure so it can't swallow unrelated bugs. |
| **D7** | `_fetch_worker` exception ladder: `except _Cancelled` → `except FetchError as exc` (calls `format_fetch_error`) → `except Exception` (generic fallback stays). Order matters. | `_Cancelled` is the most specific worker sentinel; `FetchError` is the data-layer typed exception; `Exception` is the catch-all safety net. Reordering loses the safety net or makes `FetchError` unreachable. |

## Non-obvious code shape — new `core/messages.py` (full module)

```python
"""Spanish user-facing message mapping for FetchError kinds.

Shared by CLI and GUI. Adding a new FetchError.kind without extending
_FETCH_ERROR_MESSAGES_ES is a localization spec violation.
"""
from __future__ import annotations

from .errors import FetchError


_FETCH_ERROR_MESSAGES_ES: dict[str, str] = {
    "network":    "No se pudo conectar con el servicio de SUNAT. Verifique su conexión a internet e intente de nuevo.",
    "http_4xx":   "La consulta fue rechazada por el servicio de SUNAT (HTTP {status}).",
    "http_5xx":   "El servicio de SUNAT no está disponible en este momento (HTTP {status}). Intente de nuevo más tarde.",
    "parse":      "El servicio de SUNAT devolvió una respuesta inesperada. Intente de nuevo más tarde.",
    "rate_limit": "Demasiadas solicitudes al servicio de SUNAT. Espere un momento e intente de nuevo.",
    "input":      "Parámetros de consulta inválidos.",
}

_GENERIC_FALLBACK = "Error al consultar el tipo de cambio. Intente de nuevo más tarde."


def format_fetch_error(exc: FetchError) -> str:
    template = _FETCH_ERROR_MESSAGES_ES.get(exc.kind, _GENERIC_FALLBACK)
    if exc.kind in ("http_4xx", "http_5xx") and exc.status is not None:
        return template.format(status=exc.status)
    return template
```

`cli._format_fetch_error` shim is deleted entirely; `cli.py:276` calls `format_fetch_error(exc)` directly. The `_fetch_worker` exception ladder is D7's ladder with the `FetchError` branch calling this function.

## TDD Plan (RED-first, write order)

15 RED cases. Each confirmed failing (`pytest -q`) before its implementation commit. Names match the proposal.

1. `test_get_with_retry_429_exhausted_raises_rate_limit` (B1)
2. `test_get_with_retry_5xx_exhausted_still_raises_http_5xx` (B1 regression)
3. `test_load_state_returns_default_when_state_is_list` (B4)
4. `test_load_state_returns_default_when_state_is_null` (B4)
5. `test_min_year_exported_from_validators` (B8) — asserts `core.MIN_YEAR is core.validators.MIN_YEAR`
6. `test_max_year_returns_today_year` (B9)
7. `test_fetch_range_rejects_inverted_range` (pre-existing, Q5 regression)
8. `test_format_fetch_error_maps_all_kinds` (Q4)
9. `test_format_fetch_error_substitutes_http_status` (Q4)
10. `test_cli_routes_fetch_error_through_core_messages` (Q4, replaces `test_fetch_error_maps_to_spanish_stderr`)
11. `test_save_xlsx_skips_row_with_malformed_fecha` (B2)
12. `test_save_xlsx_exits_5_on_unexpected_write_error` (B2)
13. `test_app_imports_min_year_from_core` (B8 regression)
14. `test_app_validates_against_dynamic_max_year` (B9, mocks `date.today` to year+1)
15. `test_fetch_worker_renders_spanish_message_on_fetch_error` (B3)

## PR Split

| PR | Items | LoC | Budget |
|---|---|---|---|
| **PR 1 — Data layer** | B1, B4, B8, B9, Q5 + tests 1–7 | ~120 | ≤ 400 ✓ |
| **PR 2 — Surface integration** | B2, B3, Q4 + `core/messages.py` + `cli.py` + `app.py` + tests 8–15 | ~100 | ≤ 400 ✓ |

Sequential, not stacked. PR 2 doesn't strictly import from PR 1's diff, but the proposal's success criteria assume `core.MAX_YEAR` is removed and `max_year()` is live before the GUI worker test mocks `_validate_inputs` — cleanest order is PR 1 → PR 2. Either order stays green.

## Rollback

`git revert <sha>` per PR. No data migration, no schema change, no on-disk format change. Pre-change test suite returns green after either revert.

## Out of Scope

Change B (B5–B7), Change D (D1–D5), Change E (P1–P4), Change F (G1–G10), Change G (Q1, Q2, Q7, Q8). Specifically deferred: CSV encoding without BOM, `--range` 730-day cap, CLI `--month` MIN_YEAR/MAX_YEAR bounds, `os.startfile` bare-except cleanup, English `month_abbr` in Spanish UI, `_cancelled` dead field, fetch_range unconditional sleep, `_get_with_retry` swallow-all. The new `core.MAX_YEAR` removal is breaking for any external `from core import MAX_YEAR` consumer; none exist in-repo and no external SDK ships this, so no deprecation alias is provided.
