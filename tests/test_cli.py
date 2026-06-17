"""Tests for the CLI surface (T2.1).

These tests lock in the contracts of `cli.run()`:

- Input validation exits 2 with Spanish stderr and never reaches the
  `fetch_*` helpers (input-validation R3, S5 and S6).
- The `--csv` export writes a UTF-8 BOM as the first three bytes
  (csv-export R1, S7).
- The `--help` output does NOT expose a `--csv-bom` flag
  (csv-export R2 regression guard).

The validation and BOM tests are RED on the pre-PR-2 `cli.py`:

- The pre-PR-2 range/month validation does not call
  `core.validate_range` / `core.validate_month`, so an invalid range
  such as `2025-01-01:2099-01-01` falls through to `fetch_range`, which
  raises a `FetchError` that the bare `except Exception` collapses to
  exit code 4 with a generic message.
- The pre-PR-2 `_save_csv` writes with `encoding="utf-8"` (no BOM), so
  the first three bytes are the ASCII for "Fec", not the UTF-8 BOM.

The `--csv-bom` help test is a regression guard: it is GREEN on the
current `cli.py` (no such flag exists) and stays GREEN after the
implementation, locking in the contract that the BOM is not optional
in this change cycle.
"""
from __future__ import annotations

import pytest

import cli
import core
from core import FetchError


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_cli_range_future_end_exits_2(tmp_cache_dir, capsys, monkeypatch):
    """`--range` with a future end date must exit 2 with a Spanish error
    and must NOT call `fetch_range`.
    """
    fetch_range_calls: list[tuple] = []

    def fake_fetch_range(*args, **kwargs):
        fetch_range_calls.append((args, kwargs))
        return []

    monkeypatch.setattr(core, "fetch_range", fake_fetch_range)
    monkeypatch.setattr(cli, "fetch_range", fake_fetch_range)

    exit_code = cli.run(["--range", "2025-01-01:2099-01-01"])
    captured = capsys.readouterr()

    assert exit_code == 2, (
        f"expected exit code 2, got {exit_code}; stderr={captured.err!r}"
    )
    assert "futura" in captured.err.lower(), (
        f"expected Spanish validator message in stderr, got {captured.err!r}"
    )
    assert fetch_range_calls == [], (
        "fetch_range must not be called for an invalid --range input"
    )


def test_cli_month_below_min_year_exits_2(tmp_cache_dir, capsys, monkeypatch):
    """`--month` with a year below MIN_YEAR must exit 2 with a Spanish
    error and must NOT call `fetch_month`.
    """
    fetch_month_calls: list[tuple] = []

    def fake_fetch_month(*args, **kwargs):
        fetch_month_calls.append((args, kwargs))
        return []

    monkeypatch.setattr(core, "fetch_month", fake_fetch_month)
    monkeypatch.setattr(cli, "fetch_month", fake_fetch_month)

    exit_code = cli.run(["--month", "1900-01"])
    captured = capsys.readouterr()

    assert exit_code == 2, (
        f"expected exit code 2, got {exit_code}; stderr={captured.err!r}"
    )
    err = captured.err.lower()
    assert "año" in err or "1900" in err, (
        f"expected Spanish validator message about the year, got {captured.err!r}"
    )
    assert fetch_month_calls == [], (
        "fetch_month must not be called for an invalid --month input"
    )


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def test_csv_first_bytes_are_bom(tmp_cache_dir, tmp_path, monkeypatch):
    """`--csv` must write the UTF-8 BOM (EF BB BF) as the first 3 bytes."""
    out_file = tmp_path / "out.csv"

    # Stub fetch_range to return a single row without touching the network
    # or the cache. The query (--range) is intentionally a valid past range
    # so that input validation passes and we reach the CSV write path.
    def fake_fetch_range(*args, **kwargs):
        return [{"fecha": "2024-01-15", "compra": 3.74, "venta": 3.75}]

    monkeypatch.setattr(core, "fetch_range", fake_fetch_range)
    monkeypatch.setattr(cli, "fetch_range", fake_fetch_range)

    exit_code = cli.run(
        ["--range", "2024-01-01:2024-12-31", "--csv", str(out_file)]
    )
    assert exit_code == 0, "cli.run should succeed for a valid --csv export"

    with open(out_file, "rb") as f:
        first_bytes = f.read(3)
    assert first_bytes == b"\xef\xbb\xbf", (
        f"expected UTF-8 BOM (EF BB BF) at the start of the CSV, got {first_bytes!r}"
    )


# ---------------------------------------------------------------------------
# --help regression guard
# ---------------------------------------------------------------------------


def test_help_does_not_show_csv_bom_flag(capsys):
    """`--help` must not expose a `--csv-bom` flag (csv-export R2)."""
    with pytest.raises(SystemExit) as exc_info:
        cli.run(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--csv-bom" not in captured.out, (
        f"--help must not mention --csv-bom; got {captured.out!r}"
    )


# ---------------------------------------------------------------------------
# FetchError mapping (data-fetch R1, localization R4)
# ---------------------------------------------------------------------------


def test_fetch_error_maps_to_spanish_stderr(tmp_cache_dir, capsys, monkeypatch):
    """When the data layer raises FetchError, the CLI must print a
    Spanish message to stderr and exit non-zero.
    """
    def fake_fetch_range(*args, **kwargs):
        raise FetchError(kind="http_5xx", message="HTTP 503", status=503)

    monkeypatch.setattr(core, "fetch_range", fake_fetch_range)
    monkeypatch.setattr(cli, "fetch_range", fake_fetch_range)

    exit_code = cli.run(["--range", "2024-01-01:2024-12-31"])
    captured = capsys.readouterr()

    assert exit_code != 0, (
        f"expected non-zero exit on FetchError, got {exit_code}; "
        f"stderr={captured.err!r}"
    )
    err = captured.err.lower()
    # Generic Spanish error marker; the exact wording is a design choice
    # but the string MUST be in Spanish (not the bare except's
    # "Error al consultar: ..." English-ish fallback).
    assert "error" in err, (
        f"expected an 'Error:' line in stderr, got {captured.err!r}"
    )
    # The friendly Spanish mapping uses words that the pre-PR-2 bare
    # except would NOT produce: "SUNAT", "servicio", "intente". Any of
    # these confirms we are routing through the kind->message mapper.
    assert any(
        marker in err for marker in ("sunat", "servicio", "intente")
    ), (
        f"FetchError kind=http_5xx should map to a friendly Spanish "
        f"message (must contain one of 'SUNAT', 'servicio', 'intente'); "
        f"got {captured.err!r}"
    )
