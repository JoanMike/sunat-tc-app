# Delta for docs (non-behavior)

> This is a **special non-behavior delta**. It exists to keep the SDD artifact set
> complete without polluting the behavior specs in `openspec/specs/`.

## No Spec Deltas

This change (`docs-sync-reality`) corrects documentation drift in `README.md`,
`openspec/AGENTS.md`, and `openspec/config.yaml` to reflect the post-Changes-A+B state.
No requirements are added, modified, removed, or renamed.

The existing specs in `openspec/specs/` are already synced:

- **Change A** (`fix-data-layer-bugs`) archived 2026-06-17 — synced `data-fetch`,
  `gui-worker-lifecycle`, `input-validation`, `localization`.
- **Change B** (`fix-gui-lifecycle-bugs`) archived 2026-06-17 — synced
  `app-startup-and-imports`, `gui-worker-lifecycle`, `input-validation`.

## What This Change Touches

| File | Drift item | Correction |
|------|-----------|------------|
| `README.md` | D1: `core.py` single file | `core/` package with submodules in tree + code table |
| `README.md` | D4: exit code conflates `--help` with no-args | Split: `--help` = 0, no-args = 1 |
| `openspec/AGENTS.md` | D2: testing section stale | pytest + 63 tests + strict_tdd:true |
| `openspec/AGENTS.md` | D2: "Upcoming change" section | Removed (change archived 2026-06-13) |
| `openspec/AGENTS.md` | D2: `_get_with_retry` collapses to `[]` | Now raises typed `FetchError` |
| `openspec/AGENTS.md` | D5: `openpyxl` top-level import | Lazy import in both `app.py` and `cli.py` |
| `openspec/config.yaml` | D3: testing section stale | runner=pytest, unit=true |
| `openspec/config.yaml` | D3: strict_tdd_reason references archived change | Updated to current state |

## Verification

No automated spec-scenario verification applies (no behavior change). The apply phase
verifies by: (1) `pytest -q` remains 63/63 — proves no code was touched; (2) visual
confirmation that each file reads correctly.
