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

import contextlib
import json
import sys
import tkinter as tk
from pathlib import Path

import pytest

import core

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
        with contextlib.suppress(tk.TclError):
            root.destroy()


@pytest.fixture
def app(hidden_root, tmp_cache_dir, monkeypatch):
    """Build a SunatTCApp on a per-test Toplevel with safe dialog stubs.

    Q7 (quality-lint-and-hardening D3): each test gets its own
    `tk.Toplevel(hidden_root)` instead of stacking widgets on the shared
    module-scoped root, then the Toplevel is torn down. `hidden_root` stays
    module-scoped (Python 3.14 `tcl_findLibrary` workaround). Every
    `self.root.*` call in `SunatTCApp` (`title`/`geometry`/`minsize`/
    `protocol`/`bind_all`/`after`/`update`/`destroy`) is valid on a Toplevel
    (it inherits `tk.Wm` + `tk.Misc`).
    """
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

    toplevel = tk.Toplevel(hidden_root)
    toplevel.withdraw()
    application = app_module.SunatTCApp(toplevel)
    yield application
    toplevel.destroy()


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


# ---------------------------------------------------------------------------
# T2.6/T2.7 — `_fetch_worker` FetchError branch (B3)
# ---------------------------------------------------------------------------


def test_fetch_worker_fetcherror_uses_spanish_message(app, monkeypatch):
    """When the fetch layer raises `FetchError`, `_fetch_worker` MUST
    call `on_done` with a Spanish message produced by
    `core.format_fetch_error`, NOT the raw `str(exc)` English-y text.
    The status bar should reflect that Spanish message via
    `_on_fetch_done` (gui-worker-lifecycle R3, B3).
    """
    import app as app_module
    from core import FetchError

    # Stub the underlying fetch_* helpers to raise a typed FetchError.
    # `app.py` does `from core import fetch_day, fetch_month, fetch_range`,
    # so the bound names live on `app` (not on `core`). Patch them in
    # the `app` module namespace.
    def boom_day(*a, **kw):
        raise FetchError(kind="network", message="boom")

    monkeypatch.setattr(app_module, "fetch_day", boom_day)
    monkeypatch.setattr(app_module, "fetch_month", boom_day)
    monkeypatch.setattr(app_module, "fetch_range", boom_day)

    seen: list[tuple[list[dict], str]] = []

    def capture_on_done(rows: list[dict], message: str) -> None:
        seen.append((rows, message))

    # Run the worker synchronously.
    app._fetch_worker(
        {"kind": "today"},
        token=app._worker_token,
        on_done=capture_on_done,
    )

    assert len(seen) == 1, f"expected one on_done call, got {seen!r}"
    rows, message = seen[0]
    assert rows == [], f"FetchError path must pass empty rows; got {rows!r}"

    # Must NOT echo raw `str(exc)` (which would be the English-ish "boom").
    assert "boom" not in message.lower(), (
        f"FetchError path must not echo raw str(exc); got {message!r}"
    )
    # Must contain a Spanish marker produced by core.format_fetch_error.
    assert any(
        marker in message.lower()
        for marker in ("sunat", "conexi", "intente", "verifique")
    ), (
        f"FetchError(kind='network') must map to a Spanish message via "
        f"core.format_fetch_error; got {message!r}"
    )


# ---------------------------------------------------------------------------
# B6 — _on_close signals cancel and joins the worker before destroy
# (gui-worker-lifecycle delta: set -> join(2.0) -> save_state -> destroy)
# ---------------------------------------------------------------------------


class _FakeWorker:
    """Controllable fake worker for `_on_close` tests.

    Stubs `is_alive()` / `join()` so no real thread is spawned and assertions
    are deterministic (not timing-flaky). `alive` controls `is_alive()`; `join`
    is a no-op that records the timeout it was called with. When `alive` stays
    True after `join` returns, the close path simulates a join timeout (the
    worker did not exit within the bounded window) — exactly the
    gui-worker-lifecycle "Worker stuck on a slow network" scenario.
    """

    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.join_calls: list = []

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        self.join_calls.append(timeout)
        # no-op: the real Thread.join(timeout) returns after the timeout
        # regardless of whether the thread exited; we never block the test.


def test_on_close_sets_cancel_event(app, monkeypatch):
    """`_on_close` SHALL set the cooperative cancel flag before tearing down
    (gui-worker-lifecycle delta, scenario 'Close during an in-flight fetch')."""
    import app as app_module

    app.worker = _FakeWorker(alive=True)
    # Protect the module-scoped shared root: never really destroy it, and
    # keep save_state off the (tmp) disk so the test stays focused.
    monkeypatch.setattr(app.root, "destroy", lambda: None)
    monkeypatch.setattr(app_module, "save_state", lambda state: True)

    app._on_close()

    assert app._cancel_event.is_set(), (
        "_on_close must set _cancel_event so the in-flight worker aborts at "
        "its next check point"
    )
    assert app.worker.join_calls, (
        "_on_close must call worker.join when the worker is alive"
    )


def test_on_close_joins_worker_before_destroy(app, monkeypatch):
    """`_on_close` SHALL join the worker BEFORE destroying the root, so the
    worker's terminal `root.after(0, _update)` fires while the root is alive
    and the generation-token guard harmlessly discards the stale result."""
    import app as app_module

    order: list[str] = []
    worker = _FakeWorker(alive=True)
    # Record the call order relative to save/destroy.
    worker.join = lambda timeout=None: order.append("join")  # type: ignore[assignment]
    app.worker = worker

    monkeypatch.setattr(
        app_module, "save_state", lambda state: order.append("save")
    )
    monkeypatch.setattr(app.root, "destroy", lambda: order.append("destroy"))

    app._on_close()

    assert "join" in order and "destroy" in order, (
        f"_on_close must call both join and destroy; got order={order!r}"
    )
    assert order.index("join") < order.index("destroy"), (
        f"worker.join MUST precede root.destroy so the worker's "
        f"root.after(0, _update) fires while the root is alive; "
        f"got order={order!r}"
    )


def test_on_close_destroy_still_happens_on_join_timeout(app, monkeypatch):
    """When the worker stays alive past the join timeout (stalled socket),
    `_on_close` SHALL still complete: cancel is set, join is attempted, and
    `root.destroy` still runs (the daemon worker does not block process exit)
    — gui-worker-lifecycle 'Worker stuck on a slow network' scenario."""
    import app as app_module

    # Fake worker whose is_alive() stays True even after join returns —
    # simulates a stalled socket that does not observe cancel within the
    # bounded 2.0s window.
    worker = _FakeWorker(alive=True)
    app.worker = worker

    destroyed: list[bool] = []
    monkeypatch.setattr(app_module, "save_state", lambda state: True)
    monkeypatch.setattr(app.root, "destroy", lambda: destroyed.append(True))

    app._on_close()

    assert app._cancel_event.is_set(), (
        "cancel MUST be set even when the worker does not exit in time"
    )
    assert worker.join_calls, "join MUST be attempted before destroy"
    assert destroyed, (
        "root.destroy MUST still be called after a join timeout so the close "
        "completes without hanging (daemon worker does not block exit)"
    )


# ---------------------------------------------------------------------------
# B7 — _validate_inputs uses the canonical MAX_RANGE_DAYS
# (input-validation delta: GUI range cap reads core.MAX_RANGE_DAYS, not a literal)
# ---------------------------------------------------------------------------


def test_validate_inputs_uses_max_range_days(app, monkeypatch):
    """`_validate_inputs` range-cap SHALL read the canonical `MAX_RANGE_DAYS`
    (re-exported from `core`), not a hardcoded literal, so the GUI cap and
    `core.validate_range` can never drift (input-validation delta).

    Proven by monkeypatching the app-module binding of `MAX_RANGE_DAYS` to a
    small value (10) and using a span (20 days) that exceeds the patched cap
    but is well under the real 730-day cap: the literal-`730` code would NOT
    reject a 20-day span, so only the constant-driven check can produce the
    error. The Spanish message MUST interpolate the patched value ("10")."""
    from datetime import date, timedelta

    import app as app_module

    # Patch the app-module binding (where `_validate_inputs` resolves
    # MAX_RANGE_DAYS from). raising=False so the RED run — before the
    # constant is imported into app — does not AttributeError on setattr.
    monkeypatch.setattr(app_module, "MAX_RANGE_DAYS", 10, raising=False)

    today = date.today()
    app.mode.set("range")
    app.start_date.set_date(today - timedelta(days=20))
    app.end_date.set_date(today)

    ok, msg, _params = app._validate_inputs()

    assert not ok, (
        f"a 20-day span MUST be rejected when MAX_RANGE_DAYS=10 (the "
        f"literal-730 path would not reject it); got ok={ok!r}, msg={msg!r}"
    )
    assert "10" in msg, (
        f"the Spanish error message MUST interpolate MAX_RANGE_DAYS (10); "
        f"got {msg!r}"
    )


# ---------------------------------------------------------------------------
# Change F — GUI polish UX (G1/G2/G3/G5/G10)
# ---------------------------------------------------------------------------


def test_today_label_refreshes_on_mode_change_to_today(app, monkeypatch):
    """G1: re-entering 'Hoy' mode refreshes today_label with the current
    date, so a GUI left open past midnight shows the new 'today' when the
    user re-selects Hoy (app-startup-and-imports delta)."""
    from datetime import date as real_date

    import app as app_module

    # Construction used the real date.today(); force a distinct future date
    # so a refresh is observable (the label must change from real-today to
    # the patched value).
    fixed = real_date(2099, 12, 31)

    class _FixedDate(real_date):
        @classmethod
        def today(cls):
            return fixed

    # Leave today mode first (pack the range frame, forget today_label).
    app.mode.set("range")
    app._on_mode_change()

    # Now patch date and re-enter today mode.
    monkeypatch.setattr(app_module, "date", _FixedDate)
    app.mode.set("today")
    app._on_mode_change()

    text = str(app.today_label.cget("text"))
    assert "31/12/2099" in text, (
        f"today_label must refresh to the current date on re-entering Hoy; "
        f"got {text!r}"
    )


def test_ctrl_a_selects_all_rows(app):
    """G2: `_select_all` selects every row in the tree (mirrors the
    `<Control-a>` binding), so the user can copy/export the whole result
    set with the keyboard (app-startup-and-imports delta)."""
    rows = [
        {"fecha": "2024-01-15", "compra": 3.74, "venta": 3.75},
        {"fecha": "2024-01-16", "compra": 3.76, "venta": 3.77},
        {"fecha": "2024-01-17", "compra": 3.78, "venta": 3.79},
    ]
    app.data = rows
    app._populate_table(rows)
    # Start from an explicit empty selection to prove _select_all does the work.
    app.tree.selection_set(())
    assert len(app.tree.selection()) == 0, "fixture precondition: no selection"

    app._select_all()

    assert len(app.tree.selection()) == 3, (
        f"_select_all must select all 3 rows; got {len(app.tree.selection())}"
    )


def _out_of_order_rows() -> list[dict]:
    """Three rows NOT ordered by `compra` (middle row has the lowest)."""
    return [
        {"fecha": "2024-01-15", "compra": 3.76, "venta": 3.77},
        {"fecha": "2024-01-16", "compra": 3.74, "venta": 3.75},
        {"fecha": "2024-01-17", "compra": 3.78, "venta": 3.79},
    ]


def test_sort_by_column_compra_ascending(app):
    """G3: `_sort_by_column("compra", False)` sorts `self.data` ascending by
    compra AND repopulates the tree so the `tree.index(iid) -> self.data[i]`
    invariant `_get_rows_for_copy` depends on still holds."""
    rows = _out_of_order_rows()
    app.data = rows
    app._populate_table(rows)

    app._sort_by_column("compra", False)

    # self.data is now ascending by compra.
    compras = [r["compra"] for r in app.data]
    assert compras == [3.74, 3.76, 3.78], (
        f"self.data must be sorted asc by compra; got {compras}"
    )
    # The tree display order matches self.data position-for-position, so the
    # tree.index(iid) -> self.data[i] invariant is preserved.
    children = app.tree.get_children()
    assert len(children) == 3
    for i, iid in enumerate(children):
        assert app.tree.index(iid) == i, "tree display position must be dense"
        # Copy path uses tree.index(iid) to index self.data; verify the
        # mapping yields the sorted compra values top-to-bottom.
        row = app.data[app.tree.index(iid)]
        assert row["compra"] == compras[i], (
            f"invariant broken at position {i}: tree->{row['compra']} "
            f"vs data->{compras[i]}"
        )


def test_sort_toggles_direction(app):
    """G3: clicking the same heading twice toggles `_sort_desc` and the
    heading indicator flips from `▲` (asc) to `▼` (desc)."""
    rows = _out_of_order_rows()
    app.data = rows
    app._populate_table(rows)

    app._on_heading_click("compra")
    assert app._sort_col == "compra"
    assert app._sort_desc is False
    assert "▲" in str(app.tree.heading("compra")["text"])

    app._on_heading_click("compra")
    assert app._sort_desc is True
    assert "▼" in str(app.tree.heading("compra")["text"])


def test_sort_resets_on_new_fetch(app, monkeypatch):
    """G3: a new fetch resets the sort state and clears the heading arrow,
    because fresh rows arrive fecha-asc from `fetch_range` and the visuals
    must match the actual order."""
    # Establish a sort state.
    app._sort_col = "compra"
    app._sort_desc = True

    # Drive `_on_fetch_done` (the reset site) with a fresh result set and
    # drain the scheduled `root.after(0, _update)` so `_update` runs.
    fresh = [
        {"fecha": "2024-02-01", "compra": 3.80, "venta": 3.81},
        {"fecha": "2024-02-02", "compra": 3.82, "venta": 3.83},
    ]
    app._on_fetch_done(fresh, "Se obtuvieron 2 registro(s).")
    # Bump-protect: the token captured by the closure equals the current
    # token, so `_update` runs. Drain the Tk event loop.
    app.root.update()
    app.root.update_idletasks()

    assert app._sort_col is None, "sort state must reset on new fetch"
    assert app._sort_desc is False, "sort direction must reset on new fetch"
    assert "▲" not in str(app.tree.heading("compra")["text"]) and (
        "▼" not in str(app.tree.heading("compra")["text"])
    ), "heading arrow must be cleared on new fetch"


def test_show_about_displays_version(app, monkeypatch):
    """G5: `_show_about` opens an 'Acerca de' dialog whose message contains
    the app version (`core.__version__`, the single source of truth) and the
    SUNAT source attribution (app-startup-and-imports delta, Q8 / D4)."""
    import app as app_module

    shown: dict[str, str] = {}

    def capture(title, message, **kw):
        shown["title"] = title
        shown["message"] = message

    monkeypatch.setattr(app_module.messagebox, "showinfo", capture)

    app._show_about()

    assert "title" in shown, "_show_about must call messagebox.showinfo"
    assert core.__version__ in shown["message"], (
        f"about dialog must mention core.__version__ ({core.__version__!r}); "
        f"got {shown['message']!r}"
    )
    assert "SUNAT" in shown["message"], (
        f"about dialog must mention SUNAT; got {shown['message']!r}"
    )


def test_progressbar_determinate_for_range_mode(app, monkeypatch):
    """G10: for a range fetch the progressbar MUST switch to determinate
    mode (the month count is knowable), so the user sees real progress
    instead of an infinite bounce (gui-worker-lifecycle delta)."""
    from datetime import date as real_date

    # Stub threading.Thread so no real worker (and no network) runs.
    class _FakeThread:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr("threading.Thread", _FakeThread)

    today = real_date.today()
    app.mode.set("range")
    app.start_date.set_date(today.replace(day=1))
    app.end_date.set_date(today)

    app._on_fetch()

    mode = str(app.progress.cget("mode"))
    assert mode == "determinate", (
        f"range fetch must configure the progressbar as determinate; got {mode!r}"
    )


def test_poll_progress_updates_value_for_range(app, monkeypatch):
    """G10: `_poll_progress` unpacks the `ProgressUpdate` payload and feeds
    `progress["value"]` (range mode), while still writing the status text.
    The worker never touches `self.progress` — value crosses via the
    queue (thread-safe)."""
    import app as app_module

    ProgressUpdate = app_module.ProgressUpdate  # RED: AttributeError

    # Feed a determinate payload directly into the queue.
    app.progress_queue.put(ProgressUpdate("Consultando…", 2, 5))

    # Fake-alive worker so the guard at the top of `_poll_progress` passes.
    class _LivelyThread:
        def is_alive(self) -> bool:
            return True

    app.worker = _LivelyThread()  # type: ignore[assignment]

    # Stub `root.after` so the reschedule does not keep the test alive.
    monkeypatch.setattr(app.root, "after", lambda *a, **kw: None)

    app._poll_progress()

    assert float(app.progress["value"]) == 2, (
        f"_poll_progress must feed progress['value'] from the payload; "
        f"got {app.progress['value']!r}"
    )
    assert str(app.status.cget("text")) == "Consultando…", (
        f"_poll_progress must still write the status text; got "
        f"{app.status.cget('text')!r}"
    )


def test_set_busy_resets_value_on_idle(app):
    """G10: `_set_busy(False, ...)` resets the progressbar to its idle
    default — value back to 0 and mode back to "indeterminate" — so a
    previous range's determinate bar does not linger on the next idle
    state (gui-worker-lifecycle delta).

    Note: on this Tk build `ttk.Progressbar.stop()` already zeroes
    `["value"]`, so the mode reset is the behavior that actually changes
    in RED; both halves of the idle-reset contract are asserted together.
    """
    # Precondition: a finished range fetch left a determinate, part-full bar.
    app.progress.configure(mode="determinate", maximum=10)
    app.progress["value"] = 6
    assert str(app.progress.cget("mode")) == "determinate", "fixture precondition"
    assert float(app.progress["value"]) == 6, "fixture precondition"

    app._set_busy(False, "Done")

    assert str(app.progress.cget("mode")) == "indeterminate", (
        f"_set_busy(False) must reset the progressbar mode to indeterminate "
        f"(idle default); got {app.progress.cget('mode')!r}"
    )
    assert float(app.progress["value"]) == 0, (
        f"_set_busy(False) must reset progress['value'] to 0; got "
        f"{app.progress['value']!r}"
    )


# ---------------------------------------------------------------------------
# Token de la API v2 — `_apply_token` (guardar / verificar / quitar)
# ---------------------------------------------------------------------------


def test_apply_token_saves_and_verifies(app, monkeypatch):
    """Guardar un token verificado: persiste vía core y confirma al usuario."""
    import app as app_module

    saved: list = []
    checked: list = []
    infos: list = []
    monkeypatch.setattr(app_module, "save_token", lambda v: saved.append(v) or True)
    monkeypatch.setattr(app_module, "check_token", lambda v: checked.append(v) or True)
    monkeypatch.setattr(
        app_module.messagebox, "showinfo", lambda *a, **k: infos.append(a)
    )

    app._apply_token("sk_test.abc")

    assert saved == ["sk_test.abc"], "debe persistir el token vía core.save_token"
    assert checked == ["sk_test.abc"], "debe verificar el token contra la API"
    assert infos, "debe informar al usuario que quedó guardado"
    assert "Token verificado" in str(app.status.cget("text"))


def test_apply_token_rejected_by_api_warns(app, monkeypatch):
    """Token rechazado por la API: se guarda igual pero se advierte."""
    import app as app_module

    warns: list = []
    monkeypatch.setattr(app_module, "save_token", lambda v: True)
    monkeypatch.setattr(app_module, "check_token", lambda v: False)
    monkeypatch.setattr(
        app_module.messagebox, "showwarning", lambda *a, **k: warns.append(a)
    )

    app._apply_token("sk_bad")

    assert warns, "debe advertir que la API rechazó el token"
    assert "rechazado" in str(app.status.cget("text")).lower()


def test_apply_token_unverifiable_shows_info(app, monkeypatch):
    """Sin conexión (None): se guarda y se avisa que no se pudo verificar."""
    import app as app_module

    infos: list = []
    monkeypatch.setattr(app_module, "save_token", lambda v: True)
    monkeypatch.setattr(app_module, "check_token", lambda v: None)
    monkeypatch.setattr(
        app_module.messagebox, "showinfo", lambda *a, **k: infos.append(a)
    )

    app._apply_token("sk_offline")

    assert infos, "debe informar que se guardó sin verificar"
    assert "guardado" in str(app.status.cget("text")).lower()


def test_apply_token_empty_removes_token(app, monkeypatch):
    """`_apply_token("")` borra el token sin verificar contra la red."""
    import app as app_module

    saved: list = []
    monkeypatch.setattr(app_module, "save_token", lambda v: saved.append(v) or True)
    monkeypatch.setattr(
        app_module, "check_token", lambda v: pytest.fail("borrar no debe verificar")
    )

    app._apply_token("")

    assert saved == [""], "un valor vacío borra el token (core.save_token(''))"
    assert "eliminado" in str(app.status.cget("text")).lower()


def test_apply_token_save_failure_errors(app, monkeypatch):
    """Si no se puede escribir config.json: error y no se verifica el token."""
    import app as app_module

    errors: list = []
    monkeypatch.setattr(app_module, "save_token", lambda v: False)
    monkeypatch.setattr(
        app_module, "check_token", lambda v: pytest.fail("no verificar si no se guardó")
    )
    monkeypatch.setattr(
        app_module.messagebox, "showerror", lambda *a, **k: errors.append(a)
    )

    app._apply_token("sk_test")

    assert errors, "debe mostrar error de escritura"


def test_configure_token_dialog_builds(app):
    """El diálogo «Configurar token…» se construye sin errores ni bloqueos.

    Verifica que abra un Toplevel con los botones Guardar/Quitar token y lo
    destruye enseguida para no dejar un grab activo entre tests.
    """

    def _walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from _walk(child)

    before = set(app.root.winfo_children())
    app._on_configure_token()
    nuevos = [w for w in app.root.winfo_children() if w not in before]
    assert nuevos, "debe abrirse el diálogo de token"
    try:
        textos = [
            str(w.cget("text"))
            for dlg in nuevos
            for w in _walk(dlg)
            if w.winfo_class() == "TButton"
        ]
        assert any("Guardar" in t for t in textos), f"falta «Guardar»: {textos}"
        assert any("Quitar token" in t for t in textos), (
            f"falta «Quitar token»: {textos}"
        )
    finally:
        for dlg in nuevos:
            with contextlib.suppress(tk.TclError):
                dlg.grab_release()
            dlg.destroy()
