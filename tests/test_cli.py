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


def test_cli_does_not_define_local_format_fetch_error_shim():
    """Regression guard: `cli.py` must NOT define a local `_format_fetch_error`
    shim. The single source of truth for the FetchError → Spanish message
    mapping lives in `core.messages.format_fetch_error` (Q4 / B3). If this
    test fails, someone re-introduced the dead shim — call `format_fetch_error`
    from `core` instead."""
    assert not hasattr(cli, "_format_fetch_error"), (
        "cli._format_fetch_error must be removed; use core.format_fetch_error"
    )
    # And the module-level mapping dict must be gone too.
    assert not hasattr(cli, "_FETCH_ERROR_MESSAGES_ES"), (
        "cli._FETCH_ERROR_MESSAGES_ES must be removed; lives in core.messages"
    )


# ---------------------------------------------------------------------------
# XLSX malformed-fecha guard (B2)
# ---------------------------------------------------------------------------


def test_cli_xlsx_malformed_fecha_falls_back_to_raw_string(tmp_cache_dir, tmp_path, monkeypatch):
    """`--xlsx` with a row whose `fecha` is not a valid ISO date must
    fall back to writing the raw string (mirroring `app.py:916-919`)
    instead of crashing. Pre-PR-2 the inner `datetime.strptime` raised
    ValueError that escaped the outer `except OSError`, surfacing as a
    traceback + exit 1. After the fix the file is written successfully
    with the raw `fecha` string in the cell.
    """
    out_file = tmp_path / "out.xlsx"

    def fake_fetch_range(*args, **kwargs):
        # `fecha="not-a-date"` is intentionally not ISO-parseable; the
        # per-row `try/except ValueError` in `_save_xlsx` falls back to
        # writing the raw string in the cell.
        return [
            {"fecha": "not-a-date", "compra": 3.74, "venta": 3.75},
        ]

    monkeypatch.setattr(core, "fetch_range", fake_fetch_range)
    monkeypatch.setattr(cli, "fetch_range", fake_fetch_range)

    exit_code = cli.run(
        ["--range", "2024-01-01:2024-12-31", "--xlsx", str(out_file)]
    )

    assert exit_code == 0, (
        f"malformed-fecha xlsx write should succeed (fallback to raw string); "
        f"got exit={exit_code}"
    )
    # File must exist and be non-empty (a real XLSX was written).
    assert out_file.exists(), "xlsx file should be written"
    assert out_file.stat().st_size > 0, "xlsx file should be non-empty"


def test_cli_xlsx_unexpected_write_error_exits_5(tmp_cache_dir, tmp_path, monkeypatch, capsys):
    """An unexpected ValueError / TypeError raised anywhere in the output
    write path MUST be converted to exit 5 with a Spanish
    "Error al escribir…" message (fix-data-layer-bugs D6 / README contract).
    Pre-PR-2 the outer `except OSError` did not catch ValueError, so a
    TypeError or unexpected ValueError escaped as traceback + exit 1.
    """
    out_file = tmp_path / "out.xlsx"

    def fake_fetch_range(*args, **kwargs):
        return [{"fecha": "2024-01-15", "compra": 3.74, "venta": 3.75}]

    monkeypatch.setattr(core, "fetch_range", fake_fetch_range)
    monkeypatch.setattr(cli, "fetch_range", fake_fetch_range)

    # Patch `wb.save` so the Workbook save itself raises an unexpected
    # ValueError. The widened `except (OSError, ValueError, TypeError)`
    # must convert this to exit 5.
    def boom_save(_path):
        raise ValueError("simulated unexpected write failure")

    # Lazy import shim: `_save_xlsx` imports `Workbook` lazily, so we
    # patch the symbol at the module level after import.
    from openpyxl import Workbook
    monkeypatch.setattr(Workbook, "save", boom_save)

    exit_code = cli.run(
        ["--range", "2024-01-01:2024-12-31", "--xlsx", str(out_file)]
    )
    captured = capsys.readouterr()

    assert exit_code == 5, (
        f"unexpected write error must exit 5, got {exit_code}; "
        f"stderr={captured.err!r}"
    )
    assert "error al escribir" in captured.err.lower(), (
        f"expected Spanish 'Error al escribir' in stderr, got {captured.err!r}"
    )


# ---------------------------------------------------------------------------
# Q8 — `--version` CLI flag (quality-lint-and-hardening)
# ---------------------------------------------------------------------------


def test_cli_version_flag_exits_0(capsys):
    """`--version` SHALL print `%(prog)s {__version__}` to stdout and exit 0
    WITHOUT performing any fetch or cache operation
    (app-startup-and-imports delta, Q8 / D4). argparse `action="version"`
    fires during `parse_args`, so `cli.run` raises `SystemExit(0)` before the
    query path is reached.
    """
    with pytest.raises(SystemExit) as exc_info:
        cli.run(["--version"])
    assert exc_info.value.code == 0, (
        f"--version must exit 0, got {exc_info.value.code}"
    )
    captured = capsys.readouterr()
    assert core.__version__ in captured.out, (
        f"--version stdout must contain core.__version__ ({core.__version__!r}); "
        f"got {captured.out!r}"
    )
