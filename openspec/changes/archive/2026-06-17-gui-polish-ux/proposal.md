# Proposal: GUI Polish UX (Change F)

## Intent

Five independent UX gaps in the Tkinter GUI (`app.py`): the "Hoy" date label
goes stale across midnight, the table has no `Ctrl+A` select-all, headings
cannot be re-sorted, there is no "Acerca de" dialog, and the progressbar
bounces indefinitely in range mode even though the month count is knowable.
Each is small, localized, and independently testable; together they make the
GUI feel less like a quick utility and more like an unfinished prototype.

## Scope

### In Scope
- **G1** — refresh `today_label` text when re-entering "Hoy" mode.
- **G2** — `Ctrl+A` / `Ctrl+Shift+A` select-all binding on the tree.
- **G3** — column sort on heading click (fecha/compra/venta, asc/desc) with
  ▲/▼ indicators and sort-state reset on a new fetch.
- **G5** — "Acerca de…" dialog showing app version and data source.
- **G10** — determinate progressbar for range mode; indeterminate for
  today/month.

### Out of Scope
- **Change G items** (Q1/Q2/Q7/Q8): G5 uses a temporary `_APP_VERSION`
  constant that Change G will centralize.
- **Deferred polish**: G4 (column resize/visibility), G6 (status bar
  timeouts), G7 (keyboard navigation), G8 (copy format options), G9 (theme
  toggle).
- Any `core/` public-contract change (G10 keeps the GUI-side `total_months`
  formula).
- Any CLI change, any docs change, any data migration.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `app-startup-and-imports`: ADDED requirements for G1 (today_label refresh),
  G2 (Ctrl+A select-all), G3 (heading sort, sorted order applies to
  export/copy), G5 (Acerca de dialog).
- `gui-worker-lifecycle`: ADDED requirement for G10 (determinate
  progressbar for range mode; `ProgressUpdate` payload; mode-aware
  `_set_busy`).

## Approach

Single PR, ~200 LoC, one file (`app.py`) plus `tests/test_app.py`. Strict
TDD: every item lands RED-first. All five touch only `SunatTCApp`; no
`core/` change.

- **G1** — 1 LoC: `today_label.configure(text=…)` as the first line of the
  `_on_mode_change` today-branch.
- **G2** — ~4 LoC: bind `<Control-a>`/`<Control-A>` on `self.tree` to a new
  `_select_all` calling `selection_set(get_children())`.
- **G3** — ~35 LoC: sort `self.data` in place by raw key (fecha ISO string
  is chronological; compra/venta are floats), then `_populate_table(self.data)`
  to preserve the `tree.index(iid) → self.data[i]` invariant. Track
  `_sort_col`/`_sort_desc`; rewrite heading text with ▲/▼; reset sort state
  in `_on_fetch_done._update`. **Decision: export and "Copiar todo" follow
  the sorted order** (mirrors the on-screen view — consistent UX).
- **G5** — ~12 LoC: `_APP_VERSION = "1.0.0"` module constant, "Acerca de…"
  button in the bottom bar, `_show_about` via `messagebox.showinfo` (Spanish).
- **G10** — ~40 LoC: `ProgressUpdate(msg, value, maximum)` namedtuple;
  `progress_queue` items `str → ProgressUpdate`; GUI computes
  `total_months` from `start`/`end` (mirrors `core` formula, coupling
  noted in a comment); `_on_fetch` configures determinate (range) vs
  indeterminate (today/month); `_poll_progress` writes `["value"]` when
  `value is not None`; `_set_busy(True)` starts the bar only in
  indeterminate mode (guard `cget("mode")`), `_set_busy(False)` resets
  `["value"] = 0`. The worker never touches `self.progress` — value
  crosses the thread boundary through `progress_queue`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app.py` module top | Modified | `_APP_VERSION` constant (G5). |
| `app.py:242` | Modified | `progress_queue` item type `str → ProgressUpdate` (G10). |
| `app.py:291-294, 441-442` | Modified | `today_label` refresh in today-branch (G1). |
| `app.py:361, 613-636, 678-704, 706-725, 735-744` | Modified | Progressbar mode + payload (G10). |
| `app.py:373-375, 798-799, 818-831` | Modified | Heading `command=`, sort state, repopulate (G3). |
| `app.py:405-409` | Modified | `Ctrl+A` binding (G2). |
| `app.py:411-433` | Modified | "Acerca de…" button (G5). |
| `tests/test_app.py` | Added | RED tests per item (G1/G2/G5 one each, G3 three, G10 three). |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| G3 breaks `tree.index(iid) → self.data[i]` invariant | Low | Approach 1 repopulates from sorted `self.data`; RED test asserts invariant. |
| G3 sort-state not reset on new fetch | Med | Reset `_sort_col`/indicator in `_on_fetch_done._update`; RED test. |
| G10 thread-safety: worker touches `self.progress` | Low | Worker only `put`s into `progress_queue`; main-thread `_poll_progress` writes `["value"]`. |
| G10 duplicate `total_months` formula drifts from `core` | Low | Trivial stable formula; comment the coupling. |
| G3 export order surprises users | Low | Documented decision: export/copy follow sorted view. |

## Rollback Plan

`git revert` the single PR. No data migration, no schema change, no
persistent state shape change. `progress_queue` item type is in-memory
only (never persisted).

## Dependencies

- **Change B** (post-A+B `app.py` state) — Change F touches the same file
  and assumes the post-B line numbers.

## Success Criteria

- [ ] All 5 polish items visible and working in the GUI.
- [ ] `pytest -q` green (71 existing + new RED-now-GREEN tests).
- [ ] No change to `core/` public contract or CLI.
- [ ] Review diff ~200 LoC, well under the 400-line budget.

## Review Budget

~200 changed lines << 400 budget. Low risk. Single PR, no chained PRs.
