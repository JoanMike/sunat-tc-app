# Exploration: gui-polish-ux (Change F)

> Scope: 5 GUI polish items (G1, G2, G3, G5, G10), ~200 LoC, single chained PR.
> Depends on Change B (touches the same `app.py`, post-B state). Strict TDD is
> ON (`openspec/config.yaml`): implementation is RED-first. Artifact language:
> English. Read-only investigation — no production code touched. G4/G6/G7/G8/G9
> and all Change-G items are explicitly OUT OF SCOPE.

## Current State

Five independent UX gaps in the GUI layer (`app.py`), all localized to
`SunatTCApp`. Line numbers below are the **confirmed post-A+B actuals** (the
brief's estimates were ~3 lines low).

- **G1 — `today_label` stale across midnight.** `app.py:291-294` constructs
  `self.today_label` with `text=f"Mostrará el tipo de cambio del
  {date.today().strftime('%d/%m/%Y')}"` exactly once. `_on_mode_change`
  (`app.py:436-446`) only packs/unpacks the label; the `if m == "today":`
  branch (`app.py:441-442`) does `self.today_label.pack(side=tk.LEFT)` and
  nothing else. If the app stays open past midnight, "Hoy" mode still shows
  yesterday's date.
- **G2 — no `Ctrl+A` (select all) in the tree.** The keybindings block is
  `app.py:405-409`: `<Control-c>`/`<Control-C>` on `self.tree`, plus
  `<Control-e>`/`<Control-E>` bound on `self.root`. The tree is
  `selectmode="extended"` (`app.py:371`) so multi-select is supported, but
  there is no select-all binding.
- **G3 — no column sorting on heading click.** `app.py:373-375` creates the
  three headings (`fecha`, `compra`, `venta`) with only `text=` and
  `anchor=` — no `command=` callback. Rows arrive date-sorted from
  `fetch_range` (`core/__init__.py:474` sorts by `fecha`) and the user cannot
  re-sort by compra/venta or toggle direction.
- **G5 — no "Acerca de" dialog.** The bottom bar (`app.py:411-433`) has
  Copiar/Limpiar caché/Exportar buttons plus `count_label` and `cache_label`,
  but no Help/About entry. No `__version__` exists yet (that is Change G's Q8).
- **G10 — progressbar is indeterminate despite a knowable month count.**
  `app.py:361` creates `self.progress = ttk.Progressbar(actions,
  mode="indeterminate", length=200)`. `_set_busy(True)` calls
  `self.progress.start(12)` (`app.py:627`) for the auto-bounce. The worker's
  `progress` callback (`app.py:735-744`) puts only the message string into
  `self.progress_queue: queue.Queue[str]` (`app.py:242`); `_poll_progress`
  (`app.py:706-725`) drains it and sets the status text only — no value feeds
  the bar. For range mode the user sees an infinite bounce even though the
  total month count is knowable.

## Affected Areas

- `app.py:291-294` — `today_label` construction (G1).
- `app.py:436-446` — `_on_mode_change`, today branch (G1 refresh site).
- `app.py:405-409` — keybindings block (G2 add `<Control-a>`/`<Control-A>`).
- `app.py:370-378` — Treeview headings/columns (G3 add `command=`, indicator).
- `app.py:818-831` — `_populate_table` (G3 reuse after sort; invariant carrier).
- `app.py:842-863` — `_get_rows_for_copy` (G3 invariant consumer; NOT modified).
- `app.py:798-799` — `_on_fetch_done._update` sets `self.data` + populates
  (G3 sort-state reset site).
- `app.py:411-433` — bottom bar (G5 add "Acerca de…" button).
- `app.py` module top — `_APP_VERSION = "1.0.0"` constant (G5; Change G
  centralizes later).
- `app.py:361` — Progressbar construction (G10 default mode).
- `app.py:242` — `progress_queue` item type (G10 `str` → payload).
- `app.py:706-725` — `_poll_progress` (G10 unpack payload, feed `["value"]`).
- `app.py:735-744` — `_fetch_worker.progress` callback (G10 emit payload).
- `app.py:613-636` — `_set_busy` (G10 mode-aware `start()`; reset `["value"]`).
- `app.py:678-704` — `_on_fetch` (G10 configure determinate vs indeterminate
  per `params["kind"]`).
- `tests/test_app.py` — new RED tests per item (drive tree/progress, assert on
  `self.data` / `self.progress["value"]`).

## Approaches

### G1 — refresh today_label on mode change (straightforward)

1. **Refresh inside `_on_mode_change`'s today branch** (recommended).
   - Add `self.today_label.configure(text=f"Mostrará el tipo de cambio del
     {date.today().strftime('%d/%m/%Y')}")` as the first line of the
     `if m == "today":` branch (`app.py:441`), before `pack`.
   - Pros: one line; fires whenever the user re-selects "Hoy" (the only
     realistic way "today" mode is re-entered after midnight); zero new state.
   - Cons: does not refresh while "Hoy" stays continuously selected across
     midnight with no interaction — but that is an acceptable edge (no ticker
     exists today and adding one is out of scope).
   - Effort: Low (1 LoC).

### G2 — `Ctrl+A` select all (straightforward)

1. **Bind `<Control-a>`/`<Control-A>` to a `_select_all` method** (recommended).
   - `self.tree.bind("<Control-a>", lambda e: self._select_all())` and the
     uppercase variant, added to the block at `app.py:405-409`.
   - `_select_all(self) -> None: self.tree.selection_set(self.tree.get_children())`.
   - Pros: mirrors the existing `<Control-c>` binding style; `selection_set`
     accepts the full children tuple; respects `selectmode="extended"`.
   - Cons: on some layouts `Ctrl+A` may conflict with an entry focus; binding
     on `self.tree` (not `bind_all`) scopes it to tree focus only — correct.
   - Effort: Low (~4 LoC).

### G3 — heading-click sort (real design choice)

The **critical invariant**: `_get_rows_for_copy` (`app.py:849`) maps each
selected tree iid to `self.data` via `self.tree.index(iid)`. `_populate_table`
(`app.py:818-831`) inserts at `tk.END` with **no explicit iid** and enumerates
by position, so after a populate, tree display-position N == `self.data[N]`.
Any sort MUST preserve this 1:1 positional mapping or copy/export breaks.

1. **Sort `self.data` in place, then `_populate_table(self.data)`** (recommended).
   - Add `self._sort_col: str | None = None` and `self._sort_desc: bool = False`
     in `__init__`. Add `_sort_by_column(col, descending)` that sorts
     `self.data` by the raw key (`row["fecha"]` ISO string sorts
     chronologically; `row["compra"]`/`row["venta"]` are floats), then calls
     `_populate_table(self.data)` and rewrites the three heading texts (active
     column gets ` ▲`/`▼`, others get the plain base name).
   - Each heading gets `command=lambda c=col: self._on_heading_click(c)`;
     `_on_heading_click` toggles desc when the same column is clicked again,
     else switches column and resets to asc.
   - **Sort-state reset on new fetch**: in `_on_fetch_done._update`
     (`app.py:798-799`), after `self.data = rows`, reset
     `self._sort_col = None; self._sort_desc = False` and clear heading
     indicators — new rows arrive fecha-asc from `fetch_range`, so the
     visuals must match the actual order.
   - Pros: preserves the `tree.index(iid) → self.data[i]` invariant trivially
     (repopulate re-establishes position N == self.data[N]); zebra tags
     re-stripe by display position (desired); single source of truth.
   - Cons: sorts `self.data` in place, so `_export_excel` (`app.py:936`) and
     "Copiar todo" (`app.py:883`) export in the sorted order, not always
     chronological. Acceptable (export mirrors the on-screen view) but worth
     surfacing in the proposal.
   - Effort: Med (~35 LoC: state, sort, heading rewrite, click handler, reset).

2. **Sort only the tree display, keep `self.data` in original order.**
   - Pros: export stays chronological.
   - Cons: BREAKS the `tree.index(iid) → self.data[i]` invariant — would
     require replacing it with an explicit `iid → row` map stored at insert
     time, touching `_get_rows_for_copy` and `_populate_table`. More invasive
     for a polish change. Rejected.

### G5 — "Acerca de" dialog (straightforward)

1. **Module constant + bottom-bar button + `_show_about`** (recommended).
   - Add `_APP_VERSION = "1.0.0"` near the other module constants
     (`app.py:75-83`). Add an "Acerca de…" `ttk.Button` to the bottom bar
     (`app.py:411-433`), packed `side=tk.LEFT` with padx. `_show_about` calls
     `messagebox.showinfo("Acerca de", f"Tipo de Cambio SUNAT\nVersión
     {_APP_VERSION}\n\nFuente de datos: apis.net.pe (API pública)\n\nConsulta
     el tipo de cambio oficial publicado por SUNAT.")`.
   - Pros: zero new deps; `messagebox.showinfo` is already stubbed by the `app`
     fixture, so a test can capture the call and assert the text contains the
     version + "apis.net.pe". `_APP_VERSION` is a clean placeholder for Change
     G's Q8 centralization.
   - Cons: button consumes bottom-bar width; on the 850px min width it fits
     next to the existing buttons (verify at apply time).
   - Effort: Low (~12 LoC).

### G10 — determinate progressbar for range mode (real design choice)

**Correction to the brief:** `fetch_range` (`core/__init__.py:451-456`) calls
`on_progress(msg, len(resultados))` — the 2nd argument is the **cumulative row
count so far**, NOT `month_idx`. `month_idx` and `total_months` are **local to
`fetch_range`** (`core/__init__.py:447-448`) and appear only inside the message
text `f"Consultando {nombre} {y} ({month_idx}/{total_months})…"`. The worker's
`progress` callback (`app.py:735`, `def progress(msg, _count)`) therefore
cannot read the month index from its arguments. The determinate value must be
derived another way.

The thread→Tk boundary is the other constraint: Tk is not thread-safe, so the
progressbar value MUST cross via `self.progress_queue` (currently
`queue.Queue[str]`), never by calling `self.progress.configure(...)` from the
worker thread.

1. **GUI computes `total_months` from start/end + counts callbacks; payload
   queue items** (recommended).
   - Change `progress_queue` items from `str` to a small
     `ProgressUpdate(msg, value, maximum)` `namedtuple` (or 3-tuple). The two
     drain loops that just `get_nowait()` and discard
     (`_poll_progress` `app.py:718-722`; `_on_fetch_done._update`
     `app.py:804-808`) work unchanged for any item type.
   - In `_fetch_worker`, for `kind == "range"`: compute
     `total_months = (end.year - start.year)*12 + (end.month - start.month) +
     1` (mirrors `core/__init__.py:447`); keep `month_idx = 0` (nonlocal/list);
     inside `progress()`, increment `month_idx` and `put(ProgressUpdate(msg,
     min(month_idx, total_months), total_months))`. The trailing
     "Procesando resultados…" callback (`core/__init__.py:475-476`) would push
     `month_idx == total_months + 1` → clamp to `total_months` (bar full).
   - For `kind in ("today", "month")`: single fetch, unknown duration → put
     `ProgressUpdate(msg, None, None)`; the bar stays indeterminate.
   - In `_on_fetch` (`app.py:697`), before `_set_busy(True, …)`, configure the
     bar per `params["kind"]`: range → `self.progress.configure(mode=
     "determinate", maximum=total_months, value=0)`; today/month →
     `self.progress.configure(mode="indeterminate")`.
   - In `_set_busy(True)` (`app.py:624-630`): only call `self.progress.start(12)`
     when `str(self.progress.cget("mode")) == "indeterminate"`; for determinate
     just pack (the worker feeds value via the queue). In `_set_busy(False)`
     (`app.py:631-636`): keep `self.progress.stop()` (safe no-op when not
     started) and add `self.progress["value"] = 0` reset.
   - `_poll_progress` (`app.py:718-722`): unpack the payload —
     `self.status.configure(text=upd.msg, …)`; if `upd.value is not None:
     self.progress["value"] = upd.value`; if `upd.maximum is not None:
     self.progress["maximum"] = upd.maximum`.
   - Pros: change is **entirely in `app.py`** — no `core` public-contract
     change (keeps Change F GUI-only); the worker already has
     `params["start"]`/`params["end"]`; namedtuple is self-documenting and the
     discard-drains are type-agnostic.
   - Cons: duplicates `fetch_range`'s `total_months` formula in the GUI; if
     core's month-stepping ever changes the GUI count could drift (mitigated:
     the formula is trivial and stable). Slightly more allocation per progress
     tick (negligible — one namedtuple per month).
   - Effort: Med (~40 LoC: namedtuple, worker counter, `_on_fetch` mode config,
     `_set_busy` mode guard, `_poll_progress` unpack, `_set_busy(False)` reset).

2. **Change `core.fetch_range` `on_progress` signature to
   `(msg, month_idx, total_months)`.**
   - Pros: explicit, no GUI-side formula duplication.
   - Cons: changes the data-layer public contract
     (`Callable[[str, int], None]` → `Callable[[str, int, int], None]`); out of
     scope for a GUI-polish change (Change F is GUI-only); may affect the CLI
     or other `on_progress` callers. Rejected for scope.

3. **Regex-parse `month_idx/total_months` out of the message string.**
   - Pros: zero core change, zero worker-state change.
   - Cons: fragile (couples the GUI to the exact Spanish message format; breaks
     if core rewords it); the trailing "Procesando resultados…" message has no
     numbers. Rejected.

## Recommendation

- **G1**: Approach 1 — refresh `today_label` text inside the today branch of
  `_on_mode_change`.
- **G2**: Approach 1 — bind `<Control-a>`/`<Control-A>` on `self.tree` to a
  `_select_all` that calls `selection_set(self.tree.get_children())`.
- **G3**: Approach 1 — sort `self.data` in place + `_populate_table(self.data)`,
  with `_sort_col`/`_sort_desc` state, per-heading `command=`, ▲/▼ indicators,
  and sort-state reset in `_on_fetch_done._update`.
- **G5**: Approach 1 — `_APP_VERSION = "1.0.0"` module constant + "Acerca de…"
  button + `_show_about` via `messagebox.showinfo`.
- **G10**: Approach 1 — GUI computes `total_months` from start/end and counts
  callbacks; `progress_queue` carries a `ProgressUpdate(msg, value, maximum)`
  payload; `_on_fetch` configures determinate (range) vs indeterminate
  (today/month); `_set_busy` starts the bar only in indeterminate mode and
  resets `["value"]` on idle.

## Risks

- **G3 index invariant (highest).** Any sort that reorders the tree without
  reordering `self.data` identically breaks `_get_rows_for_copy`
  (`app.py:849`). Approach 1 preserves it by repopulating from the sorted
  `self.data`. The RED test must (a) populate `self.data` out-of-order, call
  `_sort_by_column("compra", False)`, and assert `self.data` is now sorted and
  `tree.index(iid)` still maps correctly; (b) assert heading text carries the
  arrow on the active column and plain text on the others.
- **G3 sort-state reset on new fetch.** If `_sort_col`/indicator are not reset
  in `_on_fetch_done._update`, a `▼` on "compra" would lie after a new fetch
  resets to fecha-asc. Must reset there (or in `_on_fetch`).
- **G3 export order side effect.** Sorting `self.data` in place means Excel
  export and "Copiar todo" follow the sorted order. Acceptable (mirrors the
  view) but surface in the proposal for confirmation.
- **G10 thread-safety.** The worker MUST NOT touch `self.progress` directly;
  only `_poll_progress` (main thread, via `root.after`) writes `["value"]`.
  The payload crosses the boundary through `progress_queue`, which is already
  the established thread-safe channel.
- **G10 queue item type change.** `progress_queue` goes from `Queue[str]` to
  `Queue[ProgressUpdate]`. Both drain loops only `get_nowait()` and discard, so
  they are type-agnostic — but `_poll_progress` now unpacks the payload and
  must guard `value is not None`/`maximum is not None` (today/month emit
  `None`). The existing `test_poll_progress_propagates_non_empty_exception`
  stubs `get_nowait` to raise — unaffected. New tests should feed a real
  `ProgressUpdate` and assert `self.progress["value"]` and status text.
- **G10 `_set_busy` mode-awareness.** `start(12)` must be skipped for
  determinate mode or the bar auto-bounces against the fed value. Guard on
  `self.progress.cget("mode")`. `stop()` on idle is a safe no-op for
  determinate; add `self.progress["value"] = 0` reset so a previous range's
  full bar does not linger.
- **G10 duplicate `total_months` formula.** GUI mirrors `core/__init__.py:447`.
  Stable and trivial, but note the coupling in a comment so a future core
  change updates both.
- **Strict TDD**: all five land RED-first. G1/G2/G5 are direct
  assertion/behavior tests. G3 needs a stubbed-or-real tree driven via
  `_sort_by_column` + heading `configure` assertions. G10 needs a fake-alive
  worker (pattern from `test_poll_progress_propagates_non_empty_exception`) +
  a fed `ProgressUpdate`, plus a `_on_fetch` mode-configuration test that
  stubs `threading.Thread` (pattern from
  `test_quick_filter_during_worker_shows_espera`).

## Ready for Proposal

**Yes.** All five items are verified, localized, and independently testable.
Confirmed line numbers (post-A+B actuals, ~+3 vs. the brief): `today_label`
`app.py:291-294`, `_on_mode_change` today-branch `app.py:441-442`, keybindings
`app.py:405-409`, headings `app.py:373-375`, bottom bar `app.py:411-433`,
Progressbar `app.py:361`, `_fetch_worker.progress` `app.py:735-744`,
`_poll_progress` `app.py:706-725`, `_on_fetch_done._update` drain
`app.py:804-808`, `_set_busy` `app.py:613-636`. The orchestrator should tell
the user:

1. Change F is ready to move to **propose**.
2. **One factual correction vs. the brief (G10):** `fetch_range` passes
   `len(resultados)` (cumulative rows) as the callback's 2nd arg, NOT
   `month_idx` — so the determinate value is computed GUI-side from
   `start`/`end` (no `core` contract change). Confirm this is acceptable.
3. **Two open decisions to confirm at propose/spec time:**
   (a) G3 — is exporting/copying in the **sorted** order (not always
   chronological) acceptable? (b) G10 — `ProgressUpdate` as a `namedtuple`
   vs. a plain 3-tuple/dict (cosmetic).
4. G3 and G10 tests will need the fake-alive-worker / stubbed-thread harness
   already used in `tests/test_app.py`; the spec should call this out as a
   testability requirement.
