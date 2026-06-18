# Design: GUI Polish UX (Change F)

## Technical Approach

Five independent UX polish items, all confined to `SunatTCApp` in `app.py`.
No `core/` change, no CLI change. Strict TDD: each item lands RED-first in
`tests/test_app.py`. Single PR, ~200 LoC. Maps to the two delta specs:
G1/G2/G3/G5 → `app-startup-and-imports`, G10 → `gui-worker-lifecycle`.

## Files

| File | Action | Post-A+B lines | Description |
|------|--------|----------------|-------------|
| `app.py` | Modify | module top (~75-83) | `_APP_VERSION = "1.0.0"` (G5). |
| `app.py` | Modify | 242 | `progress_queue` item type `str → ProgressUpdate` (G10). |
| `app.py` | Modify | 291-294, 441-442 | `today_label` refresh in today-branch (G1). |
| `app.py` | Modify | 361 | Progressbar default mode (G10). |
| `app.py` | Modify | 373-375 | Heading `command=` + ▲/▼ (G3). |
| `app.py` | Modify | 405-409 | `Ctrl+A` binding (G2). |
| `app.py` | Modify | 411-433 | "Acerca de…" button (G5). |
| `app.py` | Modify | 613-636 | `_set_busy` mode-aware start + value reset (G10). |
| `app.py` | Modify | 678-704 | `_on_fetch` determinate/indeterminate config (G10). |
| `app.py` | Modify | 706-725 | `_poll_progress` unpack payload (G10). |
| `app.py` | Modify | 735-744 | `_fetch_worker.progress` builds payload (G10). |
| `app.py` | Modify | 798-799 | sort-state reset in `_on_fetch_done._update` (G3). |
| `app.py` | Modify | 818-831 | reuse `_populate_table` after sort (G3, not changed otherwise). |
| `app.py` | Add | new methods | `_select_all`, `_sort_by_column`, `_on_heading_click`, `_show_about` (G2/G3/G5). |
| `tests/test_app.py` | Add | end | 9 RED tests (G1×1, G2×1, G3×3, G5×1, G10×3). |

## Architecture Decisions

### D1 (G1): refresh today_label as first line of today-branch

**Choice**: `self.today_label.configure(text=f"Mostrará el tipo de cambio del {date.today().strftime('%d/%m/%Y')}")` as the first statement of the `if m == "today":` branch in `_on_mode_change`, before `pack`.
**Alternatives**: a `root.after` midnight ticker (rejected — new state + timer, out of scope; re-selecting "Hoy" is the realistic re-entry path).
**Rationale**: 1 LoC, fires exactly when "Hoy" is re-entered, zero new state.

### D2 (G2): bind Ctrl+A on tree → _select_all

**Choice**: in the keybindings block, `self.tree.bind("<Control-a>", lambda e: self._select_all())` and the uppercase variant; `_select_all` calls `self.tree.selection_set(self.tree.get_children())`.
**Alternatives**: `bind_all` (rejected — would fire while an entry has focus and conflict with select-all-in-entry semantics).
**Rationale**: mirrors the existing `<Control-c>` style; scoped to tree focus; `selection_set` accepts the full children tuple.

### D3 (G3): sort self.data in place + repopulate

**Choice**: `_sort_by_column(col, descending)` sorts `self.data` by the raw key (`row["fecha"]` ISO string sorts chronologically; `row["compra"]`/`row["venta"]` are floats), then `_populate_table(self.data)`. Track `self._sort_col: str | None = None` and `self._sort_desc: bool = False` in `__init__`. Each heading gets `command=lambda c=col: self._on_heading_click(c)`; `_on_heading_click` toggles desc when the same column is re-clicked, else switches column and resets to asc. Heading text is rewritten: active column gets ` ▲`/`▼`, others get the plain base name. Sort state is reset in `_on_fetch_done._update` after `self.data = rows`.
**Alternatives**: (a) sort only the tree display, keep `self.data` original — **rejected**: breaks the `tree.index(iid) → self.data[i]` invariant that `_get_rows_for_copy` (`app.py:849`) depends on, would need an explicit `iid → row` map touching `_populate_table` and `_get_rows_for_copy` — too invasive for polish. (b) sort tree items without sorting `self.data` — **rejected**: breaks `_get_rows_for_copy` identically.
**Rationale**: repopulating from sorted `self.data` trivially preserves the positional invariant; zebra tags re-stripe by display position (desired); single source of truth. **Orchestrator decision**: export and "Copiar todo" follow the sorted order (mirrors the view — consistent UX).

### D4 (G5): _APP_VERSION constant + bottom-bar button + _show_about

**Choice**: `_APP_VERSION = "1.0.0"` near the module constants; an "Acerca de…" `ttk.Button` packed `side=tk.LEFT` with padx in the bottom bar; `_show_about` calls `messagebox.showinfo("Acerca de", f"Tipo de Cambio SUNAT\nVersión {_APP_VERSION}\n\nFuente de datos: apis.net.pe (API pública)\n\nConsulta el tipo de cambio oficial publicado por SUNAT.")`.
**Alternatives**: read version from a `__version__.py` / package metadata (rejected — Change G's Q8 centralizes that later; a temp constant is the minimal placeholder).
**Rationale**: zero new deps; `messagebox.showinfo` is already stubbed by the `app` fixture so the test can capture the call.

### D5 (G10): ProgressUpdate namedtuple + GUI-side total_months + mode-aware _set_busy

**Choice** (orchestrator: namedtuple over plain tuple/dict for readability + type-safety):

```python
ProgressUpdate = namedtuple("ProgressUpdate", ["msg", "value", "maximum"])
# progress_queue: queue.Queue[ProgressUpdate]  (was Queue[str])
```

- `_fetch_worker`: for `kind == "range"`, compute `total_months = (end.year - start.year)*12 + (end.month - start.month) + 1` (mirrors `core/__init__.py:447`; **comment the coupling**), keep `month_idx` as a `nonlocal`/list, increment per `progress()` call, `put(ProgressUpdate(msg, min(month_idx, total_months), total_months))`. For `kind in ("today", "month")`: `put(ProgressUpdate(msg, None, None))`.
- `_on_fetch`: before `_set_busy(True, …)`, configure per `params["kind"]`: range → `self.progress.configure(mode="determinate", maximum=total_months, value=0)`; today/month → `self.progress.configure(mode="indeterminate")`.
- `_set_busy(True)`: only `self.progress.start(12)` when `str(self.progress.cget("mode")) == "indeterminate"`. `_set_busy(False)`: keep `self.progress.stop()` (safe no-op) and add `self.progress["value"] = 0`.
- `_poll_progress`: `self.status.configure(text=upd.msg, …)`; `if upd.value is not None: self.progress["value"] = upd.value`; `if upd.maximum is not None: self.progress["maximum"] = upd.maximum`.

**Alternatives**: (a) change `core.fetch_range` `on_progress` to `(msg, month_idx, total_months)` — **rejected**: changes the data-layer public contract, out of scope for a GUI-only change, may affect the CLI. (b) regex-parse `month_idx/total_months` from the Spanish message — **rejected**: fragile coupling to message wording; the trailing "Procesando resultados…" message has no numbers.
**Rationale**: change is entirely in `app.py`; the worker already has `params["start"]`/`params["end"]`; the two discard-drains (`_poll_progress:718-722`, `_on_fetch_done._update:804-808`) are type-agnostic so the item-type change is safe; **worker never touches `self.progress`** — value crosses the boundary only via `progress_queue` (thread-safety).

## Before/After Snippets

### G1 — `_on_mode_change` today-branch

```python
# before (app.py:441-442)
if m == "today":
    self.today_label.pack(side=tk.LEFT)
# after
if m == "today":
    self.today_label.configure(
        text=f"Mostrará el tipo de cambio del {date.today().strftime('%d/%m/%Y')}"
    )
    self.today_label.pack(side=tk.LEFT)
```

### G2 — binding + handler

```python
# add to app.py:405-409 block
self.tree.bind("<Control-a>", lambda e: self._select_all())
self.tree.bind("<Control-A>", lambda e: self._select_all())
# new method
def _select_all(self) -> None:
    self.tree.selection_set(self.tree.get_children())
```

### G3 — heading command + sort

```python
# headings (app.py:373-375)
self.tree.heading(c, text=base, command=lambda col=c: self._on_heading_click(col))

def _on_heading_click(self, col: str) -> None:
    if self._sort_col == col:
        self._sort_desc = not self._sort_desc
    else:
        self._sort_col, self._sort_desc = col, False
    self._sort_by_column(col, self._sort_desc)

def _sort_by_column(self, col: str, descending: bool) -> None:
    self.data.sort(key=lambda r: r[col], reverse=descending)  # fecha ISO / floats
    self._populate_table(self.data)
    for c, base in (("fecha", "Fecha"), ("compra", "Compra"), ("venta", "Venta")):
        mark = ""
        if c == self._sort_col:
            mark = " ▼" if self._sort_desc else " ▲"
        self.tree.heading(c, text=base + mark)

# reset in _on_fetch_done._update (app.py:798-799)
self.data = rows
self._sort_col, self._sort_desc = None, False
for c, base in (("fecha", "Fecha"), ("compra", "Compra"), ("venta", "Venta")):
    self.tree.heading(c, text=base)
self._populate_table(rows)
```

### G5 — version + button + handler

```python
_APP_VERSION = "1.0.0"  # near module constants; Change G centralizes later
# bottom bar
ttk.Button(bar, text="Acerca de…", command=self._show_about).pack(side=tk.LEFT, padx=4)
def _show_about(self) -> None:
    messagebox.showinfo(
        "Acerca de",
        f"Tipo de Cambio SUNAT\nVersión {_APP_VERSION}\n\n"
        "Desarrolado por: Jose Miguel Maldonado Garcia\n\n"
        "Consulta el tipo de cambio oficial publicado por SUNAT.",
    )
```

### G10 — payload + poll + set_busy

```python
ProgressUpdate = namedtuple("ProgressUpdate", ["msg", "value", "maximum"])
# self.progress_queue: queue.Queue[ProgressUpdate] = queue.Queue()

# _on_fetch (range branch)
total_months = (end.year - start.year) * 12 + (end.month - start.month) + 1  # mirrors core.fetch_range
self.progress.configure(mode="determinate", maximum=total_months, value=0)

# _set_busy(True)
if str(self.progress.cget("mode")) == "indeterminate":
    self.progress.start(12)
# _set_busy(False)
self.progress.stop()
self.progress["value"] = 0

# _poll_progress
upd = self.progress_queue.get_nowait()
self.status.configure(text=upd.msg, foreground=color)
if upd.value is not None:
    self.progress["value"] = upd.value
if upd.maximum is not None:
    self.progress["maximum"] = upd.maximum

# _fetch_worker.progress (range)
month_idx[0] += 1
self.progress_queue.put(ProgressUpdate(msg, min(month_idx[0], total_months), total_months))
```

## TDD Plan

| Item | Test (tests/test_app.py) | Assertion |
|------|--------------------------|-----------|
| G1 | `test_today_label_refreshes_on_mode_change_to_today` | set mode range, then today; label contains today's `DD/MM/YYYY` (optionally monkeypatch `date.today`). |
| G2 | `test_ctrl_a_selects_all_rows` | populate 3 rows, select none, call `app._select_all()`, `len(tree.selection()) == 3`. |
| G3 | `test_sort_by_column_compra_ascending` | `self.data` 3 rows out of order → `_sort_by_column("compra", False)` → `self.data` sorted asc AND tree rows match AND `tree.index(iid) → self.data[i]`. |
| G3 | `test_sort_toggles_direction` | call twice on same col → `_sort_desc` toggled; heading text carries ▲ then ▼. |
| G3 | `test_sort_resets_on_new_fetch` | set sort state, trigger `_on_fetch_done` → `_sort_col is None`, no arrow. |
| G5 | `test_show_about_displays_version` | monkeypatch `messagebox.showinfo` to capture, call `_show_about`, text contains `"1.0.0"` and `"SUNAT"`. |
| G10 | `test_progressbar_determinate_for_range_mode` | set mode range, `_on_fetch` with stubbed `threading.Thread`, assert `self.progress.cget("mode") == "determinate"`. |
| G10 | `test_poll_progress_updates_value_for_range` | put `ProgressUpdate(msg, 2, 5)` in queue, `_poll_progress` with fake-alive worker, `self.progress["value"] == 2`. |
| G10 | `test_set_busy_resets_value_on_idle` | call `_set_busy(False, …)`, `self.progress["value"] == 0`. |

## PR Split

Single PR, ~200 LoC. No chained PRs.

## Rollback

`git revert` the single PR. No data migration, no persisted state shape
change (`progress_queue` is in-memory only).

## Out of Scope

- Change G items (Q1/Q2/Q7/Q8); G5's `_APP_VERSION` is a temp placeholder
  that G centralizes.
- Deferred polish: G4 (column resize/visibility), G6 (status bar timeouts),
  G7 (keyboard nav), G8 (copy format options), G9 (theme toggle).
- Any `core/` public-contract change, any CLI change, any docs change.
