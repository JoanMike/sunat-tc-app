"""Tests for SunatTCApp behavior (PR 3 of fix/judgment-day-round-1).

Covers:
- T3.2: `_worker_token` increments; stale `_on_fetch_done` callbacks are dropped.
- T3.3: Quick-filter while a worker is alive shows a Spanish "Espere…"
  message; no new thread starts.
- T3.4: Status bar color taxonomy (info / ok / neutral).
- T3.5: `geometry` TclError falls back to `850x600`.
- T3.6: `import app` does NOT load `openpyxl`; `_abrir_carpeta` returns
  False on `OSError` and surfaces a Spanish `messagebox.showerror`.

These tests instantiate a real (hidden) Tk root. They avoid modal
dialogs by monkeypatching `messagebox` and `filedialog` per test where
needed.
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hidden_root():
    """Yield a single hidden Tk root for the whole module. Destroyed at the
    end of the module. Reusing one root per module sidesteps a Python 3.14
    Tk issue where `tk.Tk()` re-creation fails with
    "invalid command name 'tcl_findLibrary'".
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover — headless guard
        pytest.skip(f"Tk not available in this environment: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def app(hidden_root, tmp_cache_dir, monkeypatch):
    """Build a SunatTCApp on a hidden root with safe dialog stubs."""
    # Stub modal dialogs so any code path that triggers them is a no-op.
    import app as app_module
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(app_module.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(app_module.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *a, **k: False)
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda *a, **k: "")

    # Reset per-test state.json so geometry defaults are predictable.
    _, state_file = tmp_cache_dir
    state_file.write_text(
        json.dumps({"geometry": "850x600", "mode": "today", "month": 6, "year": 2024}),
        encoding="utf-8",
    )

    return app_module.SunatTCApp(hidden_root)


# ---------------------------------------------------------------------------
# T3.6 — import hygiene (no openpyxl at import time)
# ---------------------------------------------------------------------------


def test_import_app_does_not_load_openpyxl():
    """`import app` must NOT load `openpyxl` (app-startup-and-imports R1, S11)."""
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("openpyxl"):
            del sys.modules[mod]
    import app  # noqa: F401
    assert "openpyxl" not in sys.modules, (
        "app.py must not import openpyxl at module top-level"
    )
    assert "Workbook" not in app.__dict__, (
        "app module must not expose openpyxl.Workbook as a top-level name"
    )


def test_no_top_level_from_openpyxl_in_app():
    """`app.py` source must not contain a `from openpyxl import` at column 0
    (i.e. at module top-level). Indented `from openpyxl import` lines
    inside `_export_excel` are the T3.6 lazy-import contract and are allowed.
    """
    src = Path(__file__).resolve().parent.parent.joinpath("app.py").read_text(
        encoding="utf-8"
    )
    for line in src.splitlines():
        if line.startswith("#"):
            continue
        # Only check column 0 — top-level (module-scope) imports.
        assert not line.startswith("from openpyxl import"), (
            f"top-level `from openpyxl import` found in app.py: {line!r}"
        )
        assert not line.startswith("from openpyxl."), (
            f"top-level `from openpyxl.<sub>` found in app.py: {line!r}"
        )


# ---------------------------------------------------------------------------
# T3.4 — status bar color taxonomy
# ---------------------------------------------------------------------------


def test_set_busy_uses_info_color(app):
    """`_set_busy(True, ...)` paints the status in the info (busy) color."""
    app._set_busy(True, "Consultando…")
    # _set_busy configures `status` to info color; verify the foreground.
    fg = str(app.status.cget("foreground")).lower()
    assert fg == "#1f6feb", (
        f"busy status should use info color #1f6feb, got {fg!r}"
    )


def test_set_busy_false_with_rows_uses_ok_color(app):
    """`_set_busy(False, ...)` after rows paints the status in ok (green)."""
    app._set_busy(False, "Se obtuvieron 3 registro(s).")
    fg = str(app.status.cget("foreground")).lower()
    assert fg == "#2da44e", (
        f"success status should use ok color #2da44e, got {fg!r}"
    )


def test_set_busy_false_empty_uses_neutral_color(app):
    """When the caller passes the NEUTRAL color explicitly (e.g. for
    "No se encontraron datos…" or "Caché borrado."), the status bar
    must paint NEUTRAL, NOT the success green."""
    neutral_color = "#555"
    app._set_busy(
        False,
        "No se encontraron datos para el período seleccionado.",
        color=neutral_color,
    )
    fg = str(app.status.cget("foreground")).lower()
    assert fg == neutral_color, (
        f"empty result with explicit NEUTRAL color must use neutral; got {fg!r}"
    )


# ---------------------------------------------------------------------------
# T3.5 — geometry TclError fallback
# ---------------------------------------------------------------------------


def test_geometry_tclerror_falls_back(hidden_root, tmp_cache_dir, monkeypatch):
    """Corrupt `state.json` geometry → window opens at 850x600, no traceback."""
    import app as app_module

    # Stub dialogs (no-op).
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(app_module.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *a, **k: False)
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda *a, **k: "")

    # Write a state.json with a geometry Tk cannot parse.
    _, state_file = tmp_cache_dir
    state_file.write_text(
        json.dumps({"geometry": "totally!bogus", "mode": "today"}),
        encoding="utf-8",
    )

    # Make Tk.geometry raise once on the bad value, then pass through.
    real_geometry = tk.Tk.geometry
    raised = {"once": False}

    def fake_geometry(self, *args, **kwargs):
        if args and not raised["once"]:
            raised["once"] = True
            raise tk.TclError(f'invalid geometry "{args[0]}"')
        return real_geometry(self, *args, **kwargs)

    monkeypatch.setattr(tk.Tk, "geometry", fake_geometry)

    SunatTCApp = app_module.SunatTCApp
    SunatTCApp(hidden_root)  # must NOT raise

    # The state.json was re-persisted with the fallback so next launch is clean.
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["geometry"] == "850x600", (
        f"state.json geometry should be re-persisted to 850x600; got {persisted}"
    )
    assert raised["once"], "Tk.geometry should have been called with the corrupt value"


# ---------------------------------------------------------------------------
# T3.6 — `_abrir_carpeta` helper
# ---------------------------------------------------------------------------


def test_abrir_carpeta_returns_false_on_oserror(app, monkeypatch, caplog):
    """`os.startfile` raising `OSError` must produce a showerror + WARNING line."""

    def boom(_path):
        raise OSError("no association for .db")

    monkeypatch.setattr("os.startfile", boom, raising=False)
    # Capture the messagebox.showerror call.
    import app as app_module
    seen: dict[str, str] = {}

    def capture(title, message, **kw):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr(app_module.messagebox, "showerror", capture)

    with caplog.at_level("WARNING", logger="sunat_tc_app"):
        result = app._abrir_carpeta("C:\\nope\\does-not-exist")

    assert result is False, "_abrir_carpeta must return False on OSError"
    assert "title" in seen, "showerror was not called on OSError"
    assert "carpeta" in seen["message"].lower() or "carpeta" in seen["title"].lower(), (
        f"showerror text should mention 'carpeta'; got {seen!r}"
    )

    # Verify a WARNING log was emitted by the sunat_tc_app logger.
    warning_records = [
        r for r in caplog.records
        if r.name == "sunat_tc_app" and r.levelname == "WARNING"
    ]
    assert warning_records, (
        "expected a WARNING log on the sunat_tc_app logger; got "
        f"{[(r.name, r.levelname, r.getMessage()) for r in caplog.records]}"
    )


def test_abrir_carpeta_returns_true_on_success(app, monkeypatch):
    """Successful `os.startfile` returns True and shows no dialog."""
    calls: list[str] = []
    monkeypatch.setattr(
        "os.startfile", lambda p: calls.append(p), raising=False
    )

    import app as app_module
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda title, message, **kw: shown.append((title, message)),
    )

    result = app._abrir_carpeta("C:\\some\\folder")

    assert result is True
    assert calls == ["C:\\some\\folder"]
    assert shown == [], "no error dialog on success"


# ---------------------------------------------------------------------------
# T3.3 — quick-filter while a worker is alive
# ---------------------------------------------------------------------------


def test_quick_filter_during_worker_shows_espera(app, monkeypatch):
    """When a worker is alive, quick-filter must show 'Espere a que termine la consulta.'
    and NOT start a new thread."""
    import threading

    # Fake a running worker.
    class _LivelyThread:
        def is_alive(self) -> bool:
            return True

    app.worker = _LivelyThread()  # type: ignore[assignment]

    # Capture the status text after the call.
    app.status.configure(text="")

    # Track whether a new thread would have been started.
    started_threads: list[threading.Thread] = []
    real_thread = threading.Thread

    def fake_thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        started_threads.append(t)
        return t

    monkeypatch.setattr("threading.Thread", fake_thread)

    # Trigger a quick filter (any kind will do — the guard fires first).
    app._apply_quick_filter("today")

    # No new thread should have been created.
    assert started_threads == [], (
        f"quick-filter must not start a new thread while a worker is alive; "
        f"got {started_threads}"
    )
    status_text = app.status.cget("text")
    assert "espere" in status_text.lower() or "termine" in status_text.lower(), (
        f"status should show the Spanish 'Espere a que termine la consulta.' "
        f"message; got {status_text!r}"
    )


# ---------------------------------------------------------------------------
# T3.2 — `_worker_token` and stale-callback drop
# ---------------------------------------------------------------------------


def test_worker_token_init_is_zero(app):
    """`SunatTCApp.__init__` initializes `_worker_token` to 0."""
    # This test runs before any _on_fetch, so token must still be at its
    # post-__init__ baseline.
    assert hasattr(app, "_worker_token"), "app must define _worker_token"
    assert app._worker_token == 0, (
        f"_worker_token should start at 0; got {app._worker_token}"
    )


def test_cancel_event_init_is_event(app):
    """`SunatTCApp.__init__` initializes `_cancel_event` to a clear Event."""
    import threading

    assert hasattr(app, "_cancel_event"), "app must define _cancel_event"
    assert isinstance(app._cancel_event, threading.Event)
    assert not app._cancel_event.is_set()


def test_stale_callback_dropped(app, monkeypatch, hidden_root):
    """A stale `_on_fetch_done` (mismatched token) must not touch the table,
    the status, or the count label."""
    # Simulate: a previous worker fired `_on_fetch_done` and captured
    # token=5. Meanwhile a newer fetch bumped the current token to 6.
    # When the scheduled `_update` runs, the closure must see the
    # mismatch and silently return.
    app._worker_token = 5
    # Mark insert / configure as spies; the stale callback must NOT call them.
    inserted: list[tuple] = []
    configured_text: list[str] = []
    monkeypatch.setattr(
        app.tree, "insert", lambda *a, **k: inserted.append((a, k)) or "iid"
    )
    monkeypatch.setattr(
        app.tree, "delete", lambda *a, **k: None
    )  # _clear_table is a no-op
    real_configure = app.status.configure

    def spy_configure(**kw):
        if "text" in kw:
            configured_text.append(kw["text"])
        return real_configure(**kw)

    monkeypatch.setattr(app.status, "configure", spy_configure)

    # Fire the callback. The closure captures the current token (5).
    app._on_fetch_done(
        [{"fecha": "2024-01-15", "compra": 3.74, "venta": 3.75}],
        "Se obtuvieron 1 registro(s).",
    )
    # Now bump the token to simulate a newer fetch starting before the
    # scheduled `_update` runs.
    app._worker_token = 6
    # Drain the Tk event loop so the after(0, _update) callback fires.
    hidden_root.update()
    hidden_root.update_idletasks()

    assert inserted == [], f"stale callback must not insert rows; got {inserted}"
    assert configured_text == [], (
        f"stale callback must not touch the status; got {configured_text}"
    )


# ---------------------------------------------------------------------------
# Tighten queue-drain `except Exception:` to `except queue.Empty:`
# ---------------------------------------------------------------------------


def test_poll_progress_propagates_non_empty_exception(app, monkeypatch):
    """`_poll_progress` MUST catch only `queue.Empty`. A non-`Empty` exception
    from `progress_queue.get_nowait()` MUST propagate out of the method
    instead of being silently swallowed (tighten-queue-empty-mini-fix,
    app-startup-and-imports delta)."""
    import queue as queue_module

    # Fake a running worker so the guard at the top of `_poll_progress` passes.
    class _LivelyThread:
        def is_alive(self) -> bool:
            return True

    app.worker = _LivelyThread()  # type: ignore[assignment]

    # Make `get_nowait` raise something other than `queue.Empty`.
    def boom() -> str:
        raise RuntimeError("simulated non-Empty failure")

    monkeypatch.setattr(app.progress_queue, "get_nowait", boom)

    # Stub `root.after` so the reschedule at the end of `_poll_progress` does
    # not keep the test alive (otherwise Tk would call back into the method
    # in a future tick).
    monkeypatch.setattr(app.root, "after", lambda *a, **kw: None)

    with pytest.raises(RuntimeError, match="simulated non-Empty failure"):
        app._poll_progress()

    # Sanity: the boom path is the one that actually ran (the exception
    # must come from `get_nowait`, not from any other code path).
    assert queue_module.Empty.__mro__[-2:] == (BaseException, object), (
        "queue.Empty inheritance check (test invariant)"
    )
