# Delta for app-startup-and-imports

> Delta spec for `fix-gui-lifecycle-bugs`.
> Main spec: `openspec/specs/app-startup-and-imports/spec.md`.

## ADDED Requirements

### Requirement: `DEFAULT_STATE` geometry matches the `minsize` floor

`core.DEFAULT_STATE["geometry"]` SHALL equal the width/height passed to
`self.root.minsize(...)` in `SunatTCApp.__init__` (`850x600`). On first launch
with no `state.json`, `load_state()` returns `dict(DEFAULT_STATE)`, so the
persisted geometry MUST already be self-consistent with the runtime `minsize`
floor and the TclError fallback default — `state.json` SHALL NOT record a
stale smaller geometry that Tk immediately clamps on render.

#### Scenario: First launch with no state.json

- GIVEN no `state.json` exists in the app data directory
- WHEN `core.load_state()` is called and the GUI initializes
- THEN the window opens at `850x600` (clamped to `minsize`)
- AND the persisted `state.json` `geometry` value is `"850x600"`

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

## RENAMED Requirements

None.
