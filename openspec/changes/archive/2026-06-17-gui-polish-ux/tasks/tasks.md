# Tasks: GUI Polish UX (Change F)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~200 (app.py ~190 + tests ~120 net) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-always |
| Chain strategy | pending (single PR, under budget) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | G1 today_label refresh | PR 1 | base: post-A+B main; 1 RED + 1 GREEN |
| 2 | G2 Ctrl+A select-all | PR 1 | 1 RED + 1 GREEN |
| 3 | G3 heading sort | PR 1 | 3 RED + 1 GREEN (largest slice) |
| 4 | G5 Acerca de dialog | PR 1 | 1 RED + 1 GREEN |
| 5 | G10 determinate progressbar | PR 1 | 3 RED + 1 GREEN |
| 6 | VERIFY | PR 1 | full suite green |

> All units land in ONE PR, one commit per RED+GREEN pair (10 commits). Each
> RED commit adds a failing test; the paired GREEN commit makes it pass.

## Phase 1: G1 — today_label refresh

- [x] T1.1 RED — `tests/test_app.py`: add `test_today_label_refreshes_on_mode_change_to_today` (set mode range, then today; assert `today_label` text contains today's `DD/MM/YYYY`). Run pytest → fails.
- [x] T1.2 GREEN — `app.py`: add `self.today_label.configure(text=f"Mostrará el tipo de cambio del {date.today().strftime('%d/%m/%Y')}")` as first line of the `_on_mode_change` today-branch (`:441`). Run pytest → passes. Commit.

## Phase 2: G2 — Ctrl+A select-all

- [x] T2.1 RED — `tests/test_app.py`: add `test_ctrl_a_selects_all_rows` (populate tree with 3 rows, select none, call `app._select_all()`, assert `len(tree.selection()) == 3`). Run pytest → fails (`_select_all` missing).
- [x] T2.2 GREEN — `app.py`: bind `<Control-a>`/`<Control-A>` on `self.tree` in the keybindings block (`:405-409`); add `_select_all` calling `self.tree.selection_set(self.tree.get_children())`. Run pytest → passes. Commit.

## Phase 3: G3 — heading-click sort

- [x] T3.1 RED — `tests/test_app.py`: add `test_sort_by_column_compra_ascending` (3 rows out of order → `_sort_by_column("compra", False)` → `self.data` sorted asc, tree rows match, `tree.index(iid) → self.data[i]`), `test_sort_toggles_direction` (call twice → `_sort_desc` toggled, heading ▲ then ▼), `test_sort_resets_on_new_fetch` (set sort state → trigger `_on_fetch_done` → `_sort_col is None`, no arrow). Run pytest → 3 fail.
- [x] T3.2 GREEN — `app.py`: add `self._sort_col`/`self._sort_desc` in `__init__`; add `command=lambda c=col: self._on_heading_click(c)` to each heading (`:373-375`); implement `_on_heading_click` + `_sort_by_column(col, descending)` (sort `self.data` by raw key, `_populate_table(self.data)`, rewrite heading texts with ▲/▼); reset `_sort_col`/`_sort_desc` + clear arrows in `_on_fetch_done._update` (`:798-799`). Run pytest → passes. Commit.

## Phase 4: G5 — Acerca de dialog

- [x] T4.1 RED — `tests/test_app.py`: add `test_show_about_displays_version` (monkeypatch `messagebox.showinfo` to capture, call `_show_about`, assert text contains `"1.0.0"` and `"SUNAT"`). Run pytest → fails.
- [x] T4.2 GREEN — `app.py`: add `_APP_VERSION = "1.0.0"` near module constants; add "Acerca de…" `ttk.Button` to the bottom bar (`:411-433`); add `_show_about` via `messagebox.showinfo` (Spanish text incl. version + `apis.net.pe`). Run pytest → passes. Commit.

## Phase 5: G10 — determinate progressbar

- [x] T5.1 RED — `tests/test_app.py`: add `test_progressbar_determinate_for_range_mode` (mode range, `_on_fetch` with stubbed `threading.Thread`, assert `self.progress.cget("mode") == "determinate"`), `test_poll_progress_updates_value_for_range` (put `ProgressUpdate(msg, 2, 5)` in queue, `_poll_progress` with fake-alive worker, assert `self.progress["value"] == 2`), `test_set_busy_resets_value_on_idle` (`_set_busy(False, …)`, assert `self.progress["value"] == 0`). Run pytest → 3 fail.
- [x] T5.2 GREEN — `app.py`: add `ProgressUpdate = namedtuple(...)`; change `progress_queue` type (`:242`); in `_fetch_worker.progress` build `ProgressUpdate` with `value=month_idx`/`maximum=total_months` for range, `None`/`None` for today/month (`:735-744`); in `_on_fetch` configure determinate (range) vs indeterminate (today/month) with GUI-computed `total_months` (`:678-704`, comment the `core` coupling); in `_poll_progress` unpack payload and write `["value"]`/`["maximum"]` when not `None` (`:706-725`); in `_set_busy` start bar only when `cget("mode")=="indeterminate"`, reset `["value"]=0` on idle (`:613-636`). Run pytest → passes. Commit.

## Phase 6: VERIFY

- [x] T6.1 VERIFY — run `.\venv\Scripts\python.exe -m pytest -q`; confirm green (71 existing + 9 new = 80). Confirm no change to `core/` or `cli.py`. Confirm diff ~200 LoC.
