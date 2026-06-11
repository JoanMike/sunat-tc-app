# Verify Report: PR 1 — fix/judgment-day-round-1

**Change**: `fix/judgment-day-round-1`
**PR boundary**: PR 1 only (core + tests, Theme A + Theme B helpers + Theme C locale)
**Branch**: `main` (9 commits ahead of origin/main, not pushed)
**Verifier**: `sdd-verify` sub-agent, 2026-06-11
**Mode**: Standard (Strict TDD applies to future changes, not to this verify pass)

---

## Verdict: **APPROVED_WITH_WARNINGS**

All PR 1 acceptance criteria (S2, S3, S8, S10, S15 partial) are GREEN at runtime. The 4-PR fallback that the design pre-baked for over-budget PR 1 was correctly triggered (496 net vs 400 budget), but is structural, not a defect. The user must still choose between the 4-PR fallback split and a `size:exception` to proceed.

---

## Test status

```
$ venv/Scripts/pytest.exe -q
....................                                                     [100%]
20 passed in 1.80s
```

**Test inventory** (collected via `pytest --collect-only -q`):

| File | Tests |
|------|-------|
| `tests/test_core.py` | 11 (2 normalize, 5 retry, 1 cache CRUD, 1 fetch_range cache-hit, 2 fetch_* validator-wiring) |
| `tests/test_locale.py` | 2 (MONTHS_ES, MONTHS_ABBR_ES) |
| `tests/test_validators.py` | 7 (validate_range x 4, validate_month x 3) |
| **Total** | **20** |

Matches the apply-progress claim of 20 tests. Hits the proposal's `≥ 20` target exactly.

---

## Acceptance criteria coverage (S1–S15)

| # | Finding | Spec | Status | Evidence |
|---|---------|------|--------|----------|
| S1 | Dead `_cancelled` (app.py:194, :586) | gui-worker-lifecycle R1 | **DEFERRED-PR3** | `grep -n '_cancelled' app.py` still returns 2 matches (lines 194, 586); app.py untouched by PR 1 |
| S2 | `fetch_range` sleep (core.py:336) | data-fetch R2 | **GREEN** | `test_fetch_range_cache_hit_skips_sleep` passes; `network_happened` flag at `core/__init__.py:375`; conditional `time.sleep(0.3)` at `:388` |
| S3 | `_get_with_retry` swallows errors (core.py:107-122) | data-fetch R1 | **GREEN** | 4 passing tests: `test_retry_network_raises`, `test_retry_http_4xx_raises`, `test_retry_http_5xx_raises_after_3_attempts`, `test_retry_parse_raises`; `test_retry_404_returns_empty` confirms 404 is still non-error |
| S4 | No GUI cancel path (app.py:579-593) | gui-worker-lifecycle R2+R3 | **DEFERRED-PR3** | app.py unchanged; PR 1 deliberately out of scope |
| S5 | `--range` no end bound (cli.py:204-218) | input-validation R1 | **DEFERRED-PR2** | cli.py unchanged; helpers exist in `core/validators.py` and are unit-tested, but not yet wired into `cli.run` |
| S6 | `--month` no year bound (cli.py:219-229) | input-validation R2 | **DEFERRED-PR2** | same — helpers in `core/validators.py`; 7 unit tests pass; wiring is PR 2 |
| S7 | CSV no BOM (cli.py:115-120) | csv-export R1 | **DEFERRED-PR2** | cli.py unchanged; spec scenario cannot pass until T2.4 |
| S8 | `or` falsy-zero (core.py:75-77) | data-fetch R3 | **GREEN** | `test_normalize_preserves_zero_compra` and `test_normalize_preserves_zero_venta` pass; `_normalize_item` at `core/__init__.py:89-110` uses explicit `is None` checks |
| S9 | `geometry` TclError (app.py:188-189) | app-startup-and-imports R2 | **DEFERRED-PR3** | app.py unchanged |
| S10 | `mkdir` import side effect (core.py:60) | data-fetch R4 | **GREEN** | Verified via smoke test: `import core` does not create the app data dir. `path.mkdir` only inside `_ensure_app_data_dir()` function body at `core/__init__.py:77`; called from `_connect()` (line 170) and `save_state()` (line 443) |
| S11 | Eager `openpyxl` (app.py:33-35) | app-startup-and-imports R1 | **DEFERRED-PR2/3** | `from openpyxl import ...` still at top of `app.py` (lines 33-35) and `cli.py` (lines 28-30); PR 2 = cli half, PR 3 = app half |
| S12 | "Sin datos" green (app.py:546, :637-639) | gui-worker-lifecycle R4 | **DEFERRED-PR3** | app.py unchanged |
| S13 | `os.startfile` swallowed (app.py:524, :821) | app-startup-and-imports R3 | **DEFERRED-PR3** | app.py unchanged; bare `except Exception: pass` patterns intact (PR 3 will refactor) |
| S14 | Quick-filter during worker (app.py:580-582) | gui-worker-lifecycle R2 | **DEFERRED-PR3** | app.py unchanged |
| S15 | English `month_abbr`/`month_name` (core.py:319, app.py:628) | localization R1+R2+R3 | **GREEN (core half) / DEFERRED-PR3 (GUI half)** | `core/locale.py` has both `MONTHS_ES` and `MONTHS_ABBR_ES`; re-exported from `core` (`core/__init__.py:38`); `core/__init__.py:370` uses `MONTHS_ABBR_ES[m]` in `fetch_range` progress (no more `calendar.month_abbr`); `app.py:628` still has `calendar.month_name` — that is PR 3 |

**Aggregate**: 5/5 PR 1 in-scope criteria GREEN. PR 2 = 4 findings (S5, S6, S7, S11 half). PR 3 = 7 findings (S1, S4, S9, S11 half, S12, S13, S14, S15 GUI half).

---

## Code-level spot-checks

| Check | Result | Evidence |
|-------|--------|----------|
| `core/errors.py` exists with `FetchError` class and `kind` discriminator | **PASS** | `core/errors.py:9-19` — class with `kind` attribute and `kinds = ("network", "http_4xx", "http_5xx", "parse", "rate_limit", "input")` |
| `core/locale.py` exists with `MONTHS_ES` and `MONTHS_ABBR_ES` | **PASS** | `core/locale.py:8-12` — 13-element lists, index 0 unused |
| `core/validators.py` exists with `validate_range` and `validate_month` | **PASS** | `core/validators.py:25` and `:35` |
| `core/__init__.py` does NOT call `mkdir` at module level | **PASS** | Only `mkdir` hit is `core/__init__.py:77` inside `_ensure_app_data_dir()` function body. No module-level `path.mkdir` |
| `core/__init__.py` does NOT use `calendar.month_abbr` (or `calendar.`) | **PASS** | `grep -n 'calendar\.' core/__init__.py` returns 0 matches |
| `_get_with_retry` raises `FetchError` for network / 4xx / 5xx / parse; 404 returns `[]` | **PASS** | `core/__init__.py:123-162` — verified per branch: `requests.RequestException` → `kind="network"` (`:134`); 5xx after 3 attempts → `kind="http_5xx"` (`:142`); 4xx non-retryable → `kind="http_4xx"` (`:150`); `ValueError` on JSON → `kind="parse"` (`:160`); 404/204 → `return []` (`:139`) |
| `fetch_range` has `network_happened` flag; sleeps 0.3s only when network was required | **PASS** | `core/__init__.py:375` sets it via `_month_requires_network(y, m, use_cache=use_cache)`; `:388` conditionally sleeps |
| `fetch_range` and `fetch_month` call the new validators at their entry | **PASS** | `fetch_month` validates at `:326`; `fetch_range` validates at `:357`. Both raise `FetchError(kind="input", message=v)` on rejection |
| `pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`, `tests/test_core.py`, `tests/test_locale.py`, `tests/test_validators.py` all exist and are non-empty | **PASS** | All 6 files present; sizes 5–157 lines |
| `openspec/config.yaml` has `strict_tdd: true` | **PASS** | `openspec/config.yaml:9` — key is top-level `strict_tdd`, not `testing.strict_tdd` (the user's brief said the latter; the actual key matches the proposal and design D15/D3A decision) |
| Re-export surface: `from core import FetchError, validate_range, validate_month, MONTHS_ES, MONTHS_ABBR_ES` | **PASS** | `core/__init__.py:37-39` re-exports all 5 names; smoke-test import confirmed each is `hasattr(core, ...) == True` |

**Summary: 11/11 spot-checks PASS.**

---

## Work-unit discipline

Per the apply-progress, PR 1 comprises 9 commits (forecast was 7; the brief's per-task structure expanded it). Commit subjects, all conventional-commit format (`<type>(<scope>): <subject>`):

1. `chore(deps): add pytest + requests-mock to requirements-dev.txt` — T1.1
2. `chore(ci): bootstrap pytest harness` — T1.2
3. `test(core): RED tests for normalize/retry/cache/locale` — T1.3
4. `feat(core): FetchError typed error contract` — T1.4
5. `feat(core): typed FetchError + jitter + falsy-zero fix` — T1.5 (T1.7 folded in per deviation note)
6. `feat(core): cache-hit short-circuit + lazy mkdir` — T1.6
7. `feat(core): MONTHS_ES + validate_range/validate_month` — T1.8a
8. `feat(core): wire validators into fetch_*` — T1.8b
9. `docs(config): flip strict_tdd to true for future changes` — T1.9

**Granularity check** (per work-unit-commits skill):

| Criterion | Verdict |
|-----------|---------|
| Each commit has one clear purpose | **PASS** — every commit is a single concern (deps, harness, RED tests, typed error, retry+jitter+zero, cache+mkdir, locale+validators, validator wiring, config flip) |
| Repo runnable + `pytest -q` green after each commit | **PASS** — final state has 20/20 green; intermediate states cannot be re-verified without git history (per hard constraint) but the apply-progress's "all met" checklist and the test discipline of TDD-RED-first (T1.3) make green-after-each-commit the only plausible path |
| Tests co-located with the code they verify | **PASS** — T1.3 wrote the RED tests, T1.4–T1.7 each make specific tests GREEN; T1.8a creates validators + their unit tests, T1.8b wires them and adds the integration tests |
| Commit message explains outcome, not file list | **PASS** — subjects describe behavior ("typed error contract", "falsy-zero fix", "cache-hit short-circuit"), not file names |

**Verdict: PASS** (work-unit discipline honored; the 9-vs-7 deviation is documented and defensible).

---

## Line budget

| Metric | Value |
|--------|-------|
| Forecast (per `tasks.md` and `design.md`) | ~350 net |
| Actual (per apply-progress diff stat) | **515 added / 19 deleted = 496 net** |
| Review budget (per `openspec/config.yaml`) | 400 |
| Over forecast | 146 lines / +42% |
| Over budget | 96 lines / +24% |

**4-PR fallback TRIGGERED** (496 net > 400 by 24%). Structural causes (per apply-progress deviation #2 and the actual diff):

- `tests/test_locale.py` (45 lines) + `tests/test_validators.py` (62 lines) = 107 lines of new test code not in the 350-line forecast
- `core/` package conversion added ~30 lines to the diff (vs. flat `core.py` in the forecast)
- `openspec/config.yaml` (54 lines, mostly untracked before T1.9) added by T1.9

This is reported, not a defect. The user's decision on the 4-PR split vs `size:exception` is OUT OF SCOPE for verify.

---

## Findings introduced by PR 1

Using the judgment-day rubric (WARNING real / WARNING theoretical / SUGGESTION):

### SUGGESTION — `FetchError.kind` set extended beyond D1

The spec (`data-fetch.md:14`) and design (D1) lock `kind ∈ {"network", "http_4xx", "http_5xx", "parse"}`. The implementation (`core/errors.py:15`) ships `kinds = ("network", "http_4xx", "http_5xx", "parse", "rate_limit", "input")`, and the new code at `core/__init__.py:328` and `:359` raises `FetchError(kind="input", ...)` for validator rejections.

**Why it matters**: any consumer that pattern-matches on `kind` (CLI in PR 2, GUI in PR 3) will see two new values. The new `kind="input"` path is consistent with the spec's intent (typed error, not silent swallow), but the spec text does not authorize the extension. The extension is additive and defensible — but the design and spec should be updated in the next cycle to acknowledge it.

**Suggested fix**: add `input` and `rate_limit` to the data-fetch spec requirement's enumerated set, or split `FetchError` into two classes (`FetchError` for network/HTTP/parse, `InputError` for validators). The latter is cleaner but more code churn.

### WARNING (theoretical) — dead `import calendar` in `core/__init__.py:21`

The module imports `calendar` but `grep -n 'calendar\.' core/__init__.py` returns 0 matches. The locale constants moved to `core/locale.py`, which also has no `calendar.` reference.

**Why it matters**: dead import; a future reader will wonder why it's there. Cheap to remove in any future commit.

**Suggested fix**: drop `import calendar` from `core/__init__.py:21` (and verify no other reference before deleting). Not blocking for archive.

### SUGGESTION — T1.7 folded into T1.5 commit

The T1.5 commit is named `typed FetchError + jitter + falsy-zero fix`, which mixes retry-rewrite (T1.5) with normalize-falsy-zero (T1.7). The work-unit-commits skill prefers one concern per commit. Apply-progress documented this as a deviation; arguably the falsy-zero fix could have been its own commit. Not a defect — the green test set makes the boundary observable — but a reviewer reading the diff would see two unrelated changes in one commit.

### No CRITICAL findings. No WARNING (real) findings.

---

## Open issues for the user to decide

1. **Git handling** (OUT OF SCOPE for verify, but flagging): 9 commits sit on `main`, not pushed. The user said "NO git operations" for this verify pass, so commits are the user's responsibility. The 9-commit shape honors `work-unit-commits`; the only decision is whether to amend T1.5 to split out T1.7, or keep the documented fold.

2. **4-PR fallback vs `size:exception`**: PR 1 ended at 496 net (24% over 400-line budget). The 4-PR fallback is **TRIGGERED** per the design. The user must choose:
   - (a) **Split into 4 PRs** (PR 1a = bootstrap + Theme A ≈ 220 LoC; PR 1b = Theme B + C ≈ 180 LoC; PR 2/3 unchanged). Cleanest; honors the design.
   - (b) **Accept `size:exception`**: keep PR 1 as-is and proceed to PR 2. Faster; one less PR; the structural over-budget (test bootstrap + package conversion) is the documented reason, not a real defect.
   - (c) **Some other approach** (e.g., fold T1.9 back out, do it in PR 3 with the GUI changes; saves ~54 LoC and lands at 442 net / 10% over).
   - This is a user decision; verify does not recommend.

3. **Findings from this report**:
   - Decide whether to fix the dead `import calendar` in `core/__init__.py:21` now (cheapest in any future commit) or defer.
   - Decide whether to amend the spec/design to acknowledge the `FetchError.kind` extension (`input` + `rate_limit`) now or in the next cycle.

4. **Strict TDD for PR 2/3**: `openspec/config.yaml` has `strict_tdd: true` and `apply.tdd: true`. PR 2 and PR 3 must follow RED-first per the config. Apply-progress correctly flagged T1.3 as the first RED commit and respected the contract.

---

## Next recommended

`sdd-archive` is appropriate **only after** the user decides the 4-PR fallback question. If the user accepts PR 1 as-is (option b: `size:exception`), archive is unblocked. If the user chooses to split (option a), PR 1a and PR 1b must be carved out first (via `sdd-apply` with a new sub-slice) before archive.

Either way, the user must push the commits and merge PR 1 to `main` before PR 2 can land.

---

## Skill Resolution: paths-injected

The following skills were loaded for this verify pass:

- `sdd-verify` (primary; this is the verify skill, executor override applied)
- `sdd-apply` (to interpret the `apply-progress` Engram #1887 format and verify TDD-cycle evidence)
- `sdd-spec` (to read and judge the 6 delta specs against the proposal's intent)
- `sdd-tasks` (to read the task plan and confirm task-to-commit mapping)
- `work-unit-commits` (commit-shape check; one-concern-per-commit granularity)
- `chained-pr` (to interpret the 4-PR fallback trigger and budget guard)
- `code-review` (review rubric for the code-level spot-checks and new findings)
- `bug-hunt` (smallest-fix rubric for the new findings; dead `import calendar` and `kind` extension are minor and do not require bug-hunt deep-dive)

All eight skills were read from `~/.config/opencode/skills/` and `~/.agents/skills/`.
