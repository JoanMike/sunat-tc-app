# Delta for app-startup-and-imports

> Change F (gui-polish-ux). Four ADDED requirements covering G1 (today_label
> refresh), G2 (Ctrl+A select-all), G3 (heading sort), and G5 (Acerca de
> dialog). No existing requirement in this spec is modified or removed.

## ADDED Requirements

### Requirement: `today_label` refreshes on entering "Hoy" mode

`SunatTCApp._on_mode_change` SHALL recompute the "Hoy" hint label text with
`date.today()` every time the user selects "Hoy" mode. The label text MUST
reflect the current day, not the day the app was launched. This handles the
common case where the app stays open past midnight and the user re-selects
"Hoy"; continuous-across-midnight refresh without interaction is out of
scope.

#### Scenario: Stale label refreshes when re-selecting Hoy

- GIVEN the app has been open since yesterday and `today_label` still shows
  yesterday's date
- WHEN the user selects a different mode and then re-selects "Hoy"
- THEN `today_label` text contains today's date formatted `DD/MM/YYYY`

#### Scenario: Mode change away from Hoy does not error

- GIVEN "Hoy" mode is active and `today_label` is packed
- WHEN the user selects "Rango" mode
- THEN the label is unpacked and no exception is raised

### Requirement: `Ctrl+A` selects all tree rows

`SunatTCApp` SHALL bind `<Control-a>` and `<Control-A>` on `self.tree` to a
handler that selects every row. The handler MUST call
`self.tree.selection_set(self.tree.get_children())` so the existing
`selectmode="extended"` multi-select semantics apply. The binding SHALL be
scoped to `self.tree` (not `bind_all`) so it does not interfere with entry
focus.

#### Scenario: Ctrl+A selects every row

- GIVEN the table is populated with 3 rows and none are selected
- WHEN `_select_all()` is invoked (simulating `Ctrl+A`)
- THEN `len(self.tree.selection()) == 3`

#### Scenario: Ctrl+A on an empty table is a no-op

- GIVEN the table has no rows
- WHEN `_select_all()` is invoked
- THEN `len(self.tree.selection()) == 0` and no exception is raised

### Requirement: Column sort on heading click with view-following export

`SunatTCApp` SHALL make each Treeview heading (`fecha`, `compra`, `venta`)
clickable. A click SHALL sort `self.data` in place by the column's raw value
(`fecha` ISO string sorts chronologically; `compra`/`venta` are floats) and
repopulate the table from the sorted `self.data`, preserving the
`tree.index(iid) → self.data[i]` positional invariant. A second click on the
same column SHALL toggle direction; a click on a different column SHALL
switch to it ascending. The active column heading SHALL display a `▲` or
`▼` indicator. A new fetch SHALL reset sort state (`_sort_col = None`,
`_sort_desc = False`) and clear all indicators, because rows arrive
fecha-ascending from `core.fetch_range`.

Export ("Exportar") and "Copiar todo" SHALL follow the sorted order so the
export mirrors the on-screen view.

#### Scenario: Sort by compra ascending reorders data and tree

- GIVEN `self.data` holds three rows whose `compra` values are out of order
- WHEN `_sort_by_column("compra", False)` is invoked
- THEN `self.data` is sorted by `compra` ascending
- AND the tree display order matches `self.data`
- AND the `tree.index(iid) → self.data[i]` invariant still holds

#### Scenario: Re-clicking the active column toggles direction

- GIVEN `self._sort_col == "compra"` and `self._sort_desc == False`
- WHEN the "compra" heading is clicked again
- THEN `self._sort_desc` becomes `True` and the heading shows `▼`

#### Scenario: New fetch resets sort state

- GIVEN `self._sort_col == "venta"` and `self._sort_desc == True` with a `▼`
  indicator visible
- WHEN a new fetch completes and `_on_fetch_done._update` runs
- THEN `self._sort_col is None` and `self._sort_desc is False` and no heading
  shows an arrow

#### Scenario: Export follows the sorted order

- GIVEN the table is sorted descending by `venta`
- WHEN the user triggers "Exportar" or "Copiar todo"
- THEN the emitted rows follow the descending-`venta` order shown on screen

### Requirement: "Acerca de" dialog shows app version

`app.py` SHALL define a module-level `_APP_VERSION = "1.0.0"` constant. The
bottom bar SHALL include an "Acerca de…" `ttk.Button` that opens a
`messagebox.showinfo` dialog whose text MUST contain `_APP_VERSION` and the
data source "apis.net.pe". The dialog text SHALL be Spanish. This constant
is a temporary placeholder; Change G (Q8) will centralize versioning later.

#### Scenario: About dialog displays version and source

- GIVEN the app is initialized with `_APP_VERSION = "1.0.0"`
- WHEN `_show_about()` is invoked (simulating the button click)
- THEN a `messagebox.showinfo` call is made whose text contains `"1.0.0"`
  and `"apis.net.pe"`
