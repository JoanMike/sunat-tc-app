# Spec Delta: none — tooling / test-infra items (quality-lint-and-hardening)

> Q1 (ruff linter) and Q7 (GUI test fixture isolation) carry NO spec delta.
> They are tooling and test-infrastructure changes, not behavior contracts, so
> no `openspec/specs/<domain>/spec.md` is created or modified for them.
> Recorded here for traceability. References: exploration Q1/Q7; Engram
> `sdd/quality-lint-and-hardening/explore` (#1969).

## Q1 — ruff linter (no spec delta)

Adding `ruff` to `requirements-dev.txt`, creating `ruff.toml`, flipping
`openspec/config.yaml` `testing.quality.linter.available` to `true`, and
fixing/`# noqa`-ing findings is a development-workflow / quality-gate change.
It introduces no new user- or data-layer behavior. The gate is operational:
`ruff check .` exits 0 over the final code state. No `Given/When/Then` scenario
applies.

## Q7 — GUI test fixture isolation (no spec delta)

Rewriting the `tests/test_app.py` `app` fixture to build each `SunatTCApp` on a
per-test `tk.Toplevel(hidden_root)` with `toplevel.destroy()` teardown is a
test-only refactor. It changes no production behavior and no published contract.
The proof of correctness is that the existing 80 tests stay green. No
`Given/When/Then` scenario applies.

## Out of Scope

- Promoting either item to a behavior contract in a future change is not
  precluded, but is not part of Change G.
