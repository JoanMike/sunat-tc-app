"""
Aplicación GUI para consultar el Tipo de Cambio Oficial de SUNAT.

Modos de consulta:
  - Hoy
  - Rango de días (desde / hasta)
  - Mes completo (mes / año)

Funciones:
  - Copiar filas seleccionadas o todas al portapapeles
  - Exportar a archivo Excel (.xlsx) con formato
  - Caché local SQLite (consultas repetidas son instantáneas)
  - Filtros rápidos pre-armados (Hoy, Ayer, Últ. 7d, etc.)
  - Recuerda la última consulta y posición de ventana

Fuente de datos: https://api.apis.net.pe/v1/tipo-cambio-sunat
(API pública que replica el tipo de cambio oficial publicado por SUNAT).
Con un token opcional (botón «Configurar token…») las consultas de mes y
rango usan la API v2 y se resuelven en una petición por mes.

La capa de datos vive en el paquete `core/`; este archivo sólo contiene el GUI.
"""

from __future__ import annotations

import calendar
import contextlib
import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from collections import namedtuple
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Callable

# `openpyxl` is imported lazily inside `_export_excel` (T3.6,
# app-startup-and-imports R1, S11). The GUI/CSV paths must not pay
# the import cost; `import app` must not load openpyxl at all.
from core import (
    CACHE_DB,
    MAX_RANGE_DAYS,
    MIN_YEAR,
    MONTHS_ES,
    STATE_FILE,
    FetchError,
    __version__,
    cache_clear,
    cache_count,
    cache_date_range,
    check_token,
    fetch_day,
    fetch_month,
    fetch_range,
    format_fetch_error,
    get_api_token,
    load_state,
    max_year,
    save_state,
    save_token,
    setup_logging,
)

# ---------------------------------------------------------------------------
# Interfaz gráfica
# ---------------------------------------------------------------------------


class _Cancelled(Exception):
    """Sentinel raised from the worker's progress callback when the user
    clicks `Cancelar`. The worker catches it and routes to
    `on_done([], "Consulta cancelada.")`."""

    pass


# T3.4 — status bar color taxonomy (gui-worker-lifecycle R4, S12).
# Centralized so theme changes are one-edit; matching the brief's
# acceptance ("empty result paints neutral gray, not green").
_COLOR_INFO = "#1f6feb"      # busy / progress / "Cancelando…"
_COLOR_OK = "#2da44e"        # success — N rows obtained
_COLOR_NEUTRAL = "#555"      # "Sin datos", "Caché borrado.", "No se encontraron datos…"


# T3.6 — single logger for the `os.startfile` warning path. The spec
# accepts either a structured logger or a `print(..., file=sys.stderr)`;
# the logger is more configurable and matches stdlib best practice.
_logger = logging.getLogger("sunat_tc_app")

# G10 (gui-polish-ux): progress payload crossing the worker→Tk boundary.
# The worker MUST NOT touch `self.progress` directly (Tk is not
# thread-safe); `value`/`maximum` cross only via `progress_queue`, which
# `_poll_progress` drains on the main thread. `value`/`maximum` are None
# for today/month (indeterminate bar).
ProgressUpdate = namedtuple("ProgressUpdate", ["msg", "value", "maximum"])

# G3 (gui-polish-ux): (column id, base heading text) pairs used to rewrite
# heading texts with the ▲/▼ sort indicator and to clear it on a new fetch.
# Kept in sync with the headings created in `_build_ui`.
_COLUMN_LABELS: tuple[tuple[str, str], ...] = (
    ("fecha", "Fecha"),
    ("compra", "Compra (S/)"),
    ("venta", "Venta (S/)"),
)

class DateEntry(ttk.Frame):
    """
    Selector de fecha con tres Spinbox (DD / MM / YYYY).

    - Sin dependencias externas.
    - Los Spinbox limitan el rango con flechas; el día se ajusta solo cuando
      cambia el mes o el año (p. ej. 31 -> 28 en febrero).
    - set_date(d) y get_date() permiten programar/recuperar el valor.
    """

    def __init__(
        self,
        parent: tk.Misc,
        default: date | None = None,
        min_year: int = MIN_YEAR,
        max_year: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        if max_year is None:
            max_year = date.today().year
        if default is None:
            default = date.today()
        self._min_year = min_year
        self._max_year = max_year

        self._day_var = tk.StringVar(value=f"{default.day:02d}")
        self._month_var = tk.StringVar(value=f"{default.month:02d}")
        self._year_var = tk.StringVar(value=str(default.year))

        self._day = ttk.Spinbox(
            self,
            from_=1,
            to=31,
            width=3,
            justify="center",
            textvariable=self._day_var,
        )
        self._day.pack(side=tk.LEFT)
        ttk.Label(self, text="/").pack(side=tk.LEFT, padx=2)
        self._month = ttk.Spinbox(
            self,
            from_=1,
            to=12,
            width=3,
            justify="center",
            textvariable=self._month_var,
        )
        self._month.pack(side=tk.LEFT)
        ttk.Label(self, text="/").pack(side=tk.LEFT, padx=2)
        self._year = ttk.Spinbox(
            self,
            from_=min_year,
            to=max_year,
            width=5,
            justify="center",
            textvariable=self._year_var,
        )
        self._year.pack(side=tk.LEFT)

        # Ajustar el día máximo cuando cambia mes/año
        self._month_var.trace_add("write", lambda *_: self._adjust_day())
        self._year_var.trace_add("write", lambda *_: self._adjust_day())
        # Al perder foco, normalizar lo escrito
        for w in (self._day, self._month, self._year):
            w.bind("<FocusOut>", lambda _e: self._normalize())
        self._adjust_day()

    # -- lógica interna -------------------------------------------------------
    def _adjust_day(self) -> None:
        """Recalcula el día máximo permitido según mes/año actuales."""
        try:
            m = int(self._month_var.get())
            y = int(self._year_var.get())
        except (ValueError, tk.TclError):
            return
        try:
            last_day = calendar.monthrange(y, m)[1]
        except ValueError:
            return
        self._day.configure(to=last_day)
        try:
            cur = int(self._day_var.get())
            if cur > last_day:
                self._day_var.set(f"{last_day:02d}")
        except (ValueError, tk.TclError):
            pass

    def _normalize(self) -> None:
        """Rellena con ceros a la izquierda si el usuario escribió 1 dígito."""
        for var, width in (
            (self._day_var, 2),
            (self._month_var, 2),
        ):
            v = var.get().strip()
            if v.isdigit() and len(v) < width:
                var.set(v.zfill(width))
        try:
            y = int(self._year_var.get())
            if not (self._min_year <= y <= self._max_year):
                self._year_var.set(str(min(max(y, self._min_year), self._max_year)))
        except (ValueError, tk.TclError):
            pass

    # -- API pública ----------------------------------------------------------
    def get_date(self) -> date | None:
        try:
            d = int(self._day_var.get())
            m = int(self._month_var.get())
            y = int(self._year_var.get())
            return date(y, m, d)
        except (ValueError, tk.TclError):
            return None

    def set_date(self, value: date) -> None:
        # Importante: año y mes antes que el día, para que _adjust_day
        # (disparado por los trace_add) calcule el día máximo correcto.
        # Si fuera al revés, el día se clamparía con el mes/año anterior.
        self._year_var.set(str(value.year))
        self._month_var.set(f"{value.month:02d}")
        self._adjust_day()
        self._day_var.set(f"{value.day:02d}")
        self._adjust_day()


class SunatTCApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Tipo de Cambio SUNAT - Jose Miguel Maldonado Garcia")

        # Cargar estado persistido (ventana, modo, fechas)
        self.state = load_state()
        # T3.5 (app-startup-and-imports R2, S9): if the persisted geometry
        # is not parseable by Tk (e.g. older releases, manual edits),
        # fall back to 850x600 and re-persist so the next launch is clean.
        # No traceback escapes to the user.
        try:
            self.root.geometry(self.state.get("geometry", "850x600"))
        except tk.TclError:
            self.state["geometry"] = "850x600"
            self.root.geometry("850x600")
            # Re-persist so the next launch reads a clean value.
            save_state(self.state)
        self.root.minsize(850, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.data: list[dict] = []
        # G3 (gui-polish-ux): heading-click sort state. Reset on every new
        # fetch (see `_on_fetch_done._update`) because fresh rows arrive
        # fecha-asc from `fetch_range` and the visuals must match.
        self._sort_col: str | None = None
        self._sort_desc: bool = False
        self.worker: threading.Thread | None = None
        # Worker generation token (T3.2, gui-worker-lifecycle R3, S4 partial).
        # Incremented before each Thread.start(); `_on_fetch_done`'s `_update`
        # closure captures it and discards the result if a newer fetch has
        # already started (or the current one was cancelled).
        self._worker_token: int = 0
        # Cooperative cancel flag (T3.2). The worker checks this between
        # fetch_* calls and after each on_progress; the Cancelar button
        # (T3.3) sets it.
        self._cancel_event: threading.Event = threading.Event()
        self.progress_queue: queue.Queue[ProgressUpdate] = queue.Queue()

        self._configure_style()
        self._build_ui()
        self._restore_state()
        self._on_mode_change()
        self._update_cache_label()

    # -- estilo ---------------------------------------------------------------
    def _configure_style(self) -> None:
        style = ttk.Style()
        with contextlib.suppress(tk.TclError):
            style.theme_use("vista")  # nativo en Windows
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=24)
        style.configure("TButton", padding=(10, 5))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    # -- construcción UI ------------------------------------------------------
    def _build_ui(self) -> None:
        # Frame superior: modo + fechas + acciones.
        # Usamos una sola columna (column=0) con sticky distinto por fila para
        # que los radio buttons NO se desplacen cuando cambian los controles
        # de fecha de abajo.
        top = ttk.LabelFrame(self.root, text="Consulta", padding=12)
        top.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 6))
        top.columnconfigure(0, weight=1)

        # --- Modo (row 0) ---
        self.mode = tk.StringVar(value="today")
        mode_box = ttk.Frame(top)
        mode_box.grid(row=0, column=0, sticky="w", pady=(0, 6))
        modes = [("Hoy", "today"), ("Rango de días", "range"), ("Mes completo", "month")]
        for label, val in modes:
            ttk.Radiobutton(
                mode_box,
                text=label,
                value=val,
                variable=self.mode,
                command=self._on_mode_change,
            ).pack(side=tk.LEFT, padx=(0, 14))

        # --- Controles de fecha (row 1) ---
        self.date_box = ttk.Frame(top)
        self.date_box.grid(row=1, column=0, sticky="w", pady=4)

        # -- Hoy
        self.today_label = ttk.Label(
            self.date_box,
            text=f"Mostrará el tipo de cambio del {date.today().strftime('%d/%m/%Y')}",
        )

        # -- Rango
        self.range_frame = ttk.Frame(self.date_box)
        ttk.Label(self.range_frame, text="Desde:").grid(row=0, column=0, padx=(0, 4))
        self.start_date = DateEntry(
            self.range_frame,
            default=date.today().replace(day=1),
        )
        self.start_date.grid(row=0, column=1, padx=(0, 14))
        ttk.Label(self.range_frame, text="Hasta:").grid(row=0, column=2, padx=(0, 4))
        self.end_date = DateEntry(
            self.range_frame,
            default=date.today(),
        )
        self.end_date.grid(row=0, column=3, padx=(0, 4))

        # -- Mes completo
        self.month_frame = ttk.Frame(self.date_box)
        ttk.Label(self.month_frame, text="Mes:").grid(row=0, column=0, padx=(0, 4))
        self.month_spin = ttk.Spinbox(
            self.month_frame, from_=1, to=12, width=4, justify="center"
        )
        self.month_spin.grid(row=0, column=1, padx=(0, 14))
        self.month_spin.set(date.today().month)
        ttk.Label(self.month_frame, text="Año:").grid(row=0, column=2, padx=(0, 4))
        self.year_spin = ttk.Spinbox(
            self.month_frame,
            from_=MIN_YEAR,
            to=max_year(),
            width=6,
            justify="center",
        )
        self.year_spin.grid(row=0, column=3, padx=(0, 4))
        self.year_spin.set(date.today().year)

        # --- Filtros rápidos (row 2) ---
        quick = ttk.Frame(top)
        quick.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(quick, text="Filtros rápidos:").pack(side=tk.LEFT, padx=(0, 6))
        for label, kind in [
            ("Hoy", "today"),
            ("Ayer", "yesterday"),
            ("Últ. 7 días", "last7"),
            ("Últ. 30 días", "last30"),
            ("Este mes", "this_month"),
            ("Mes pasado", "last_month"),
        ]:
            ttk.Button(
                quick,
                text=label,
                command=lambda k=kind: self._apply_quick_filter(k),
            ).pack(side=tk.LEFT, padx=(0, 4))

        # --- Acciones (row 3) ---
        actions = ttk.Frame(top)
        actions.grid(row=3, column=0, sticky="we", pady=(10, 0))
        self.fetch_btn = ttk.Button(
            actions, text="Consultar", style="Accent.TButton", command=self._on_fetch
        )
        self.fetch_btn.pack(side=tk.LEFT)
        # T3.3: Cancelar button — visible only while a worker is alive
        # (gui-worker-lifecycle R2, S4 + S14).
        self.cancel_btn = ttk.Button(
            actions, text="Cancelar", command=self._on_cancel
        )
        # Hidden by default; _set_busy(True, ...) packs it next to Consultar.
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=200)
        self.status = ttk.Label(actions, text="Listo", foreground="#555")
        self.status.pack(side=tk.LEFT, padx=12)

        # Tabla de resultados
        table_frame = ttk.LabelFrame(self.root, text="Resultados", padding=6)
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=12, pady=6)

        cols = ("fecha", "compra", "venta")
        self.tree = ttk.Treeview(
            table_frame, columns=cols, show="headings", selectmode="extended"
        )
        self.tree.heading("fecha", text="Fecha", anchor="center",
                          command=lambda c="fecha": self._on_heading_click(c))
        self.tree.heading("compra", text="Compra (S/)", anchor="center",
                          command=lambda c="compra": self._on_heading_click(c))
        self.tree.heading("venta", text="Venta (S/)", anchor="center",
                          command=lambda c="venta": self._on_heading_click(c))
        self.tree.column("fecha", width=160, anchor="center")
        self.tree.column("compra", width=140, anchor="e")
        self.tree.column("venta", width=140, anchor="e")

        # Tags con colores alternados
        self.tree.tag_configure("odd", background="#f7f7fa")
        self.tree.tag_configure("even", background="#ffffff")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # Menú contextual (clic derecho)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(
            label="Copiar selección", command=self._copy_selection
        )
        self.context_menu.add_command(label="Copiar todo", command=self._copy_all)
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Exportar a Excel…", command=self._export_excel
        )

        # Atajos de teclado
        self.tree.bind("<Control-c>", lambda e: self._copy_selection())
        self.tree.bind("<Control-C>", lambda e: self._copy_selection())
        # G2 (gui-polish-ux): select-all scoped to the tree (not bind_all,
        # so an entry keeping focus still gets native select-all-in-entry).
        self.tree.bind("<Control-a>", lambda e: self._select_all())
        self.tree.bind("<Control-A>", lambda e: self._select_all())
        # Ctrl+E anclado al árbol (como Ctrl+C/A): con bind_all se disparaba
        # incluso al teclear en los spinboxes de fecha.
        self.tree.bind("<Control-e>", lambda e: self._export_excel())
        self.tree.bind("<Control-E>", lambda e: self._export_excel())

        # Barra inferior
        bottom = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bottom, text="Copiar selección", command=self._copy_selection).pack(
            side=tk.LEFT
        )
        ttk.Button(bottom, text="Copiar todo", command=self._copy_all).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(
            bottom, text="Limpiar caché",
            command=self._on_clear_cache,
        ).pack(side=tk.LEFT, padx=(6, 0))
        # Token opcional de la API v2: mes/rango en 1 petición por mes.
        ttk.Button(
            bottom, text="Configurar token…",
            command=self._on_configure_token,
        ).pack(side=tk.LEFT, padx=(6, 0))
        # G5 (gui-polish-ux): "Acerca de…" entry in the bottom bar.
        ttk.Button(
            bottom, text="Acerca de…", command=self._show_about
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            bottom, text="Exportar a Excel…", command=self._export_excel
        ).pack(side=tk.RIGHT)

        self.count_label = ttk.Label(bottom, text="", foreground="#555")
        self.count_label.pack(side=tk.RIGHT, padx=12)

        self.cache_label = ttk.Label(bottom, text="", foreground="#888", cursor="hand2")
        self.cache_label.pack(side=tk.RIGHT, padx=12)
        self.cache_label.bind("<Button-1>", lambda _e: self._show_cache_info())

    # -- manejo de modo -------------------------------------------------------
    def _on_mode_change(self) -> None:
        # Ocultar todos
        for w in (self.today_label, self.range_frame, self.month_frame):
            w.pack_forget()
        m = self.mode.get()
        if m == "today":
            # G1 (gui-polish-ux): refresh on every re-entry so a GUI left
            # open past midnight shows the new "today" when the user
            # re-selects Hoy.
            self.today_label.configure(
                text=f"Mostrará el tipo de cambio del {date.today().strftime('%d/%m/%Y')}"
            )
            self.today_label.pack(side=tk.LEFT)
        elif m == "range":
            self.range_frame.pack(side=tk.LEFT)
        else:
            self.month_frame.pack(side=tk.LEFT)

    # -- filtros rápidos ------------------------------------------------------
    def _apply_quick_filter(self, kind: str) -> None:
        """Aplica un preset: ajusta modo + fechas y dispara la consulta."""
        today = date.today()
        if kind == "today":
            self.mode.set("today")
            self._on_mode_change()
        elif kind == "yesterday":
            d = today - timedelta(days=1)
            self.mode.set("range")
            self._on_mode_change()
            self.start_date.set_date(d)
            self.end_date.set_date(d)
        elif kind == "last7":
            self.mode.set("range")
            self._on_mode_change()
            self.start_date.set_date(today - timedelta(days=6))
            self.end_date.set_date(today)
        elif kind == "last30":
            self.mode.set("range")
            self._on_mode_change()
            self.start_date.set_date(today - timedelta(days=29))
            self.end_date.set_date(today)
        elif kind == "this_month":
            self.mode.set("month")
            self._on_mode_change()
            self.month_spin.set(today.month)
            self.year_spin.set(today.year)
        elif kind == "last_month":
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            self.mode.set("month")
            self._on_mode_change()
            self.month_spin.set(last_prev.month)
            self.year_spin.set(last_prev.year)
        # Dispara la consulta
        self._on_fetch()

    # -- persistencia de estado -----------------------------------------------
    def _restore_state(self) -> None:
        """Restaura modo + fechas desde el state cargado."""
        mode = self.state.get("mode", "today")
        if mode not in ("today", "range", "month"):
            mode = "today"
        self.mode.set(mode)
        if mode == "range":
            rs = self.state.get("range_start")
            re_ = self.state.get("range_end")
            if rs:
                with contextlib.suppress(ValueError):
                    self.start_date.set_date(date.fromisoformat(rs))
            if re_:
                with contextlib.suppress(ValueError):
                    self.end_date.set_date(date.fromisoformat(re_))
        elif mode == "month":
            td = date.today()
            try:
                self.month_spin.set(int(self.state.get("month", td.month)))
                self.year_spin.set(int(self.state.get("year", td.year)))
            except (ValueError, TypeError):
                pass

    def _on_close(self) -> None:
        """Persiste geometría + modo + fechas antes de cerrar."""
        # B6 (gui-worker-lifecycle delta): signal cooperative cancel and join
        # the in-flight worker BEFORE destroying the root. The worker's
        # terminal on_done schedules `root.after(0, _update)` from the worker
        # thread; if destroy() runs first, `root.after` raises a silent
        # TclError in the worker. Joining first lets the worker observe cancel
        # at its next check point and fire on_done while the root is alive, so
        # the generation-token guard harmlessly discards the stale result.
        # Bounded 2.0s timeout so a stalled socket cannot hang the close; the
        # worker is a daemon thread, so a timed-out join never blocks process
        # exit. Mirrors the liveness guard already in `_on_cancel`.
        self._cancel_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)
        self.state["geometry"] = self.root.geometry()
        self.state["mode"] = self.mode.get()
        if self.mode.get() == "range":
            sd = self.start_date.get_date()
            ed = self.end_date.get_date()
            if sd:
                self.state["range_start"] = sd.isoformat()
            if ed:
                self.state["range_end"] = ed.isoformat()
        elif self.mode.get() == "month":
            try:
                self.state["month"] = int(self.month_spin.get())
                self.state["year"] = int(self.year_spin.get())
            except (ValueError, tk.TclError):
                pass
        if not save_state(self.state):
            # Fallo de escritura al cerrar (disco lleno, permisos): no hay
            # UI ya para avisar, pero debe quedar rastro en el log.
            _logger.warning("No se pudo persistir el estado en %s", STATE_FILE)
        self.root.destroy()

    # -- caché ----------------------------------------------------------------
    def _update_cache_label(self) -> None:
        n = cache_count()
        dmin, dmax = cache_date_range()
        if n == 0:
            self.cache_label.configure(text="Caché: vacío")
        else:
            self.cache_label.configure(
                text=f"Caché: {n} días ({dmin} → {dmax})"
            )

    def _on_clear_cache(self) -> None:
        n = cache_count()
        if n == 0:
            messagebox.showinfo("Caché", "El caché ya está vacío.")
            return
        if not messagebox.askyesno(
            "Limpiar caché",
            f"Vas a borrar {n} entradas del caché.\n"
            "Las próximas consultas a fechas pasadas irán a la API.\n\n"
            "¿Continuar?",
        ):
            return
        cache_clear()
        self._update_cache_label()
        self.status.configure(text="Caché borrado.", foreground=_COLOR_NEUTRAL)

    def _show_cache_info(self) -> None:
        n = cache_count()
        dmin, dmax = cache_date_range()
        msg = (
            f"Entradas: {n}\n"
            f"Rango: {dmin or '-'}  →  {dmax or '-'}\n\n"
            f"Ubicación:\n{CACHE_DB}"
        )
        if messagebox.askyesno("Caché local", msg + "\n\n¿Abrir carpeta?"):
            self._abrir_carpeta(str(CACHE_DB.parent))

    def _show_about(self) -> None:
        """G5 (gui-polish-ux): 'Acerca de' dialog — version + data source."""
        messagebox.showinfo(
            "Acerca de",
            f"Tipo de Cambio SUNAT\nVersión {__version__}\n\n"
            "Desarrollado por: Jose Miguel Maldonado Garcia\n\n"
            "Consulta el tipo de cambio oficial publicado por SUNAT.",
        )

    # -- token de la API v2 ---------------------------------------------------
    def _on_configure_token(self) -> None:
        """Diálogo para guardar/quitar el token de la API v2 (ver `_apply_token`).

        El token se guarda en config.json junto al caché; nunca en el código.
        """
        current = get_api_token()
        dlg = tk.Toplevel(self.root)
        dlg.title("Token de la API v2 (opcional)")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frm,
            justify=tk.LEFT,
            text=(
                "Con un token, «Mes completo» y los rangos se consultan en\n"
                "una petición por mes (segundos). Sin token se reconstruyen\n"
                "día a día (más lento por el límite de la API pública)."
            ),
        ).pack(anchor="w")
        ttk.Label(
            frm,
            text=("Token configurado." if current else "Sin token configurado."),
            foreground=_COLOR_NEUTRAL,
        ).pack(anchor="w", pady=(6, 0))
        token_var = tk.StringVar(value=current or "")
        entry = ttk.Entry(frm, textvariable=token_var, width=48, show="•")
        entry.pack(fill=tk.X, pady=(6, 0))
        entry.focus_set()

        def guardar() -> None:
            value = token_var.get().strip()
            if not value:
                messagebox.showwarning(
                    "Token", "Escriba un token o use «Quitar token»."
                )
                return
            dlg.destroy()
            self._apply_token(value)

        def quitar() -> None:
            dlg.destroy()
            self._apply_token("")

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btns, text="Guardar", command=guardar).pack(side=tk.LEFT)
        ttk.Button(btns, text="Quitar token", command=quitar).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.RIGHT)
        # Modality best-effort: `grab_set` exige una ventana ya mapeada y el
        # WM puede no haberlo hecho todavía (p. ej. con el padre oculto en
        # tests); el diálogo funciona igual sin el grab.
        with contextlib.suppress(tk.TclError):
            dlg.grab_set()

    def _apply_token(self, value: str) -> None:
        """Guarda (o borra, con "") el token y lo verifica contra la API v2."""
        if not save_token(value):
            messagebox.showerror(
                "Token",
                f"No se pudo guardar la configuración en:\n{STATE_FILE.parent}",
            )
            return
        if not value:
            messagebox.showinfo(
                "Token", "Token eliminado. Se usará la API pública (v1)."
            )
            self.status.configure(text="Token eliminado.", foreground=_COLOR_NEUTRAL)
            return
        veredicto = check_token(value)
        if veredicto is True:
            messagebox.showinfo(
                "Token",
                "Token guardado y verificado. «Mes completo» y los rangos\n"
                "se consultarán en 1 petición por mes (más rápido).",
            )
            self.status.configure(text="Token verificado.", foreground=_COLOR_OK)
        elif veredicto is False:
            messagebox.showwarning(
                "Token",
                "El token fue guardado, pero la API lo rechazó.\n"
                "Revísalo: puede estar mal copiado, vencido o sin cuota.",
            )
            self.status.configure(
                text="Token rechazado por la API.", foreground=_COLOR_NEUTRAL
            )
        else:
            messagebox.showinfo(
                "Token",
                "Token guardado, pero no se pudo verificar (¿sin conexión?).\n"
                "Se usará en la próxima consulta.",
            )
            self.status.configure(text="Token guardado.", foreground=_COLOR_OK)

    # T3.6 — single helper for the two `os.startfile` call sites
    # (cache-info and export-complete). On `OSError` (or any subclass)
    # the failure is observable: WARNING log line + Spanish
    # `messagebox.showerror`. Returns True on success, False on failure.
    def _abrir_carpeta(self, path: str) -> bool:
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            _logger.warning("os.startfile failed for %s: %s", path, exc)
            messagebox.showerror(
                "Error al abrir carpeta",
                f"No se pudo abrir la carpeta:\n{path}",
            )
            return False
        return True

    def _show_context_menu(self, event) -> None:
        if not self.data:
            return
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    # -- fetching -------------------------------------------------------------
    def _set_busy(
        self,
        busy: bool,
        message: str = "",
        color: str | None = None,
    ) -> None:
        # T3.4: callers may pass `color` explicitly (e.g. NEUTRAL for
        # "Sin datos" / "Caché borrado."). The default still maps:
        # busy=True → INFO, busy=False → OK.
        if color is None:
            color = _COLOR_INFO if busy else _COLOR_OK
        if busy:
            self.fetch_btn.configure(state="disabled")
            self.progress.pack(side=tk.LEFT, padx=10)
            # G10 (gui-polish-ux): only auto-bounce for indeterminate mode;
            # determinate mode is fed its value via the progress queue.
            if str(self.progress.cget("mode")) == "indeterminate":
                self.progress.start(12)
            # T3.3: Cancelar is visible only while a worker is alive.
            self.cancel_btn.pack(side=tk.LEFT, padx=(6, 0))
            self.status.configure(text=message, foreground=color)
        else:
            self.fetch_btn.configure(state="normal")
            self.progress.stop()
            # G10 (gui-polish-ux): reset to the idle default so a previous
            # range's determinate bar (value + mode) does not linger. The
            # next fetch reconfigures the mode per its kind.
            self.progress["value"] = 0
            self.progress.configure(mode="indeterminate")
            self.progress.pack_forget()
            self.cancel_btn.pack_forget()
            self.status.configure(text=message, foreground=color)

    def _on_cancel(self) -> None:
        """T3.3: cooperative cancel. Sets the cancel event; the worker
        observes it at the next safe check point and routes to
        `on_done([], "Consulta cancelada.")`."""
        if not (self.worker and self.worker.is_alive()):
            return
        self._cancel_event.set()
        self.status.configure(text="Cancelando…", foreground=_COLOR_INFO)

    def _validate_inputs(self) -> tuple[bool, str, dict]:
        """Valida los inputs según el modo. Devuelve (ok, msg_error, params)."""
        m = self.mode.get()
        if m == "today":
            return True, "", {"kind": "today"}

        if m == "range":
            sd = self.start_date.get_date()
            ed = self.end_date.get_date()
            if sd is None or ed is None:
                return False, "Alguna de las fechas es inválida.", {}
            if sd > ed:
                return False, "'Desde' no puede ser mayor que 'Hasta'.", {}
            if ed > date.today():
                return False, "La fecha 'Hasta' no puede ser futura.", {}
            if (ed - sd).days > MAX_RANGE_DAYS:
                return False, f"El rango máximo es de 2 años ({MAX_RANGE_DAYS} días).", {}
            return True, "", {"kind": "range", "start": sd, "end": ed}

        # month
        try:
            mo = int(self.month_spin.get())
            yr = int(self.year_spin.get())
        except ValueError:
            return False, "Mes y año deben ser numéricos.", {}
        if not (1 <= mo <= 12):
            return False, "El mes debe estar entre 1 y 12.", {}
        if not (MIN_YEAR <= yr <= max_year()):
            return False, f"El año debe estar entre {MIN_YEAR} y {max_year()}.", {}
        return True, "", {"kind": "month", "year": yr, "month": mo}

    def _on_fetch(self) -> None:
        if self.worker and self.worker.is_alive():
            # T3.3: explicit-cancel-only (cached decision 2A). Show a
            # Spanish "Espere a que termine la consulta." message and
            # return — do NOT auto-cancel, do NOT auto-restart.
            self.status.configure(
                text="Espere a que termine la consulta.", foreground=_COLOR_INFO
            )
            return
        ok, err, params = self._validate_inputs()
        if not ok:
            messagebox.showwarning("Datos inválidos", err)
            return
        # T3.2: bump the generation token and clear any stale cancel flag
        # BEFORE starting the thread. The token is captured by the
        # `_on_fetch_done` closure; if a newer fetch starts while this
        # worker is still in flight, its late callback is discarded.
        self._worker_token += 1
        self._cancel_event.clear()
        # G10 (gui-polish-ux): configure the progressbar per fetch kind.
        # Range knows the month count → determinate; today/month are single
        # shots → indeterminate. `total_months` mirrors core.fetch_range's
        # month count (core/__init__.py) — keep both in sync if core's
        # month-stepping ever changes. Configured BEFORE `_set_busy(True)`
        # so the mode-aware `start(12)` guard skips auto-bounce for range.
        if params["kind"] == "range":
            start = params["start"]
            end = params["end"]
            total_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
            self.progress.configure(mode="determinate", maximum=total_months, value=0)
        else:
            self.progress.configure(mode="indeterminate")
        self._set_busy(True, "Consultando SUNAT…")
        self._clear_table()
        self.worker = threading.Thread(
            target=self._fetch_worker, args=(params, self._worker_token, self._on_fetch_done),
            daemon=True,
        )
        self.worker.start()
        self._poll_progress()

    def _poll_progress(self) -> None:
        """
        Lee mensajes de progreso y actualiza el status mientras el worker esté vivo.

        Importante: el chequeo de `worker.is_alive()` se hace al INICIO, no al final.
        Si el worker ya terminó, salimos sin tocar el status — así el mensaje
        final puesto por _on_fetch_done (vía _set_busy) no se sobrescribe con un
        "Procesando…" viejo que haya quedado en la cola.
        """
        if not (self.worker and self.worker.is_alive()):
            return
        try:
            while True:
                # G10 (gui-polish-ux): items are ProgressUpdate payloads.
                # The worker never touches self.progress; value/maximum
                # cross the thread→Tk boundary only through this queue.
                payload = self.progress_queue.get_nowait()
                self.status.configure(text=payload.msg, foreground=_COLOR_INFO)
                if payload.value is not None:
                    self.progress["value"] = payload.value
                if payload.maximum is not None:
                    self.progress["maximum"] = payload.maximum
        except queue.Empty:
            pass
        # Reagendar. Si entre el check del inicio y ahora el worker murió,
        # la próxima iteración saldrá por el guard de arriba.
        self.root.after(120, self._poll_progress)

    def _fetch_worker(
        self,
        params: dict,
        token: int,
        on_done: Callable[[list[dict], str], None],
    ) -> None:
        kind = params["kind"]
        # G10 (gui-polish-ux): for range mode, count progress callbacks to
        # feed a determinate bar. `total_months` mirrors core.fetch_range's
        # month count (core/__init__.py) — keep both in sync if core's
        # month-stepping ever changes. `month_idx` is a mutable closure cell
        # so the nested `progress` callback can increment it.
        if kind == "range":
            start = params["start"]
            end = params["end"]
            total_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
            month_idx = [0]
        else:
            total_months = 0
            month_idx = [0]

        def progress(msg: str, _count: int) -> None:
            # T3.3: cooperative cancel. If the user pressed Cancelar
            # between fetch calls (or between on_progress invocations
            # for fetch_range), abort by signalling a sentinel back to
            # the worker. fetch_range is synchronous, so the abort
            # surfaces when it returns; the post-loop check below
            # short-circuits before the on_done call.
            if self._cancel_event.is_set():
                raise _Cancelled()
            # G10: emit a ProgressUpdate. Range feeds value/maximum (clamped
            # so the trailing "Procesando resultados…" tick fills the bar);
            # today/month emit None/None and stay indeterminate. The worker
            # never touches self.progress.
            if kind == "range":
                month_idx[0] += 1
                self.progress_queue.put(
                    ProgressUpdate(
                        msg, min(month_idx[0], total_months), total_months
                    )
                )
            else:
                self.progress_queue.put(ProgressUpdate(msg, None, None))

        try:
            if self._cancel_event.is_set():
                on_done([], "Consulta cancelada.")
                return
            if kind == "today":
                progress("Consultando día actual…", 0)
                rows = fetch_day(date.today().isoformat())
            elif kind == "month":
                progress(
                    f"Consultando {MONTHS_ES[params['month']]} {params['year']}…", 0
                )
                # El mes se reconstruye día a día (la API v1 ya no soporta
                # `?month=&year=`), así que se pasan los ticks por día: la
                # barra/estado muestran la fecha en curso y `Cancelar` surte
                # efecto en el siguiente día (no al terminar el mes completo).
                rows = fetch_month(
                    params["year"], params["month"], on_progress=progress
                )
            else:  # range
                rows = fetch_range(params["start"], params["end"], on_progress=progress)
        except _Cancelled:
            on_done([], "Consulta cancelada.")
            return
        except FetchError as exc:
            # GUI surfaces a Spanish message via core.messages (B3 / Q4);
            # do NOT fall back to raw `str(exc)` (English-y technical text).
            # Specific exception order: _Cancelled → FetchError → Exception.
            on_done([], format_fetch_error(exc))
            return
        except Exception as exc:  # noqa: BLE001
            on_done([], f"Error inesperado: {exc}")
            return
        if self._cancel_event.is_set():
            on_done([], "Consulta cancelada.")
            return
        if not rows:
            on_done([], "No se encontraron datos para el período seleccionado.")
        else:
            on_done(rows, f"Se obtuvieron {len(rows)} registro(s).")

    def _on_fetch_done(self, rows: list[dict], message: str) -> None:
        # Vuelve al hilo principal. The `_update` closure captures the
        # current `_worker_token`; if a newer fetch has started, the
        # token mismatches and the stale result is silently dropped
        # (T3.2, gui-worker-lifecycle R3, S4 partial).
        captured_token = self._worker_token
        # T3.4: choose the color from the outcome kind. Empty results,
        # cancellation, and unexpected errors paint NEUTRAL; success
        # (rows obtained) paints OK. The worker doesn't need to know
        # the colors — `_on_fetch_done` is the single source of truth.
        status_color = _COLOR_OK if rows else _COLOR_NEUTRAL

        def _update() -> None:
            if captured_token != self._worker_token:
                return
            self.data = rows
            # G3 (gui-polish-ux): fresh rows arrive fecha-asc from
            # `fetch_range`; drop any sort state + heading arrow so the
            # visuals match the actual order.
            self._reset_sort_state()
            self._populate_table(rows)
            self._set_busy(False, message, color=status_color)
            self.count_label.configure(text=f"{len(rows)} fila(s)")
            # Drenar cualquier mensaje de progreso pendiente para que
            # una iteración tardía de _poll_progress no pinte nada viejo.
            try:
                while True:
                    self.progress_queue.get_nowait()
            except queue.Empty:
                pass

        self.root.after(0, _update)

    # -- tabla ----------------------------------------------------------------
    def _clear_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.count_label.configure(text="")

    def _populate_table(self, rows: list[dict]) -> None:
        self._clear_table()
        for i, row in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert(
                "",
                tk.END,
                values=(
                    self._format_fecha_display(row["fecha"]),
                    f"{row['compra']:.4f}",
                    f"{row['venta']:.4f}",
                ),
                tags=(tag,),
            )

    @staticmethod
    def _format_fecha_display(iso_str: str) -> str:
        try:
            d = datetime.strptime(iso_str[:10], "%Y-%m-%d").date()
            return d.strftime("%d/%m/%Y")
        except ValueError:
            return iso_str

    # -- ordenación por columna (G3) -----------------------------------------
    def _on_heading_click(self, col: str) -> None:
        """Toggle direction when the same column is re-clicked, else switch
        column and reset to ascending."""
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col, self._sort_desc = col, False
        self._sort_by_column(col, self._sort_desc)

    def _sort_by_column(self, col: str, descending: bool) -> None:
        """Sort `self.data` by the raw column key, then repopulate from the
        sorted list so the `tree.index(iid) -> self.data[i]` invariant that
        `_get_rows_for_copy` depends on is preserved (`fecha` is an ISO
        string and sorts chronologically; `compra`/`venta` are floats).
        Finally rewrite the heading texts with an ▲/▼ indicator on the
        active column."""
        self.data.sort(key=lambda r: r[col], reverse=descending)
        self._sort_col = col
        self._sort_desc = descending
        self._populate_table(self.data)
        self._rewrite_headings()

    def _rewrite_headings(self) -> None:
        for c, base in _COLUMN_LABELS:
            mark = ""
            if c == self._sort_col:
                mark = " ▼" if self._sort_desc else " ▲"
            self.tree.heading(c, text=base + mark)

    def _reset_sort_state(self) -> None:
        """Clear sort state + heading indicators (called on a new fetch)."""
        self._sort_col, self._sort_desc = None, False
        for c, base in _COLUMN_LABELS:
            self.tree.heading(c, text=base)

    # -- portapapeles ---------------------------------------------------------
    def _select_all(self) -> None:
        """G2 (gui-polish-ux): select every row in the tree. Bound to
        `<Control-a>`/`<Control-A>` on `self.tree`. `selection_set`
        accepts the full children tuple."""
        self.tree.selection_set(self.tree.get_children())

    def _get_rows_for_copy(self, selected_only: bool) -> list[list[str]]:
        if not self.data:
            return []
        if selected_only:
            sel = self.tree.selection()
            if not sel:
                return []
            indices = [self.tree.index(iid) for iid in sel]
            rows = [self.data[i] for i in indices]
        else:
            rows = self.data
        out: list[list[str]] = []
        out.append(["Fecha", "Compra", "Venta"])
        for r in rows:
            out.append(
                [
                    self._format_fecha_display(r["fecha"]),
                    f"{r['compra']:.4f}",
                    f"{r['venta']:.4f}",
                ]
            )
        return out

    def _copy_to_clipboard(self, rows: list[list[str]]) -> None:
        if not rows:
            messagebox.showinfo("Sin datos", "No hay filas para copiar.")
            return
        text = "\n".join("\t".join(r) for r in rows)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # asegurar que el portapapeles persista
        n = len(rows) - 1  # descontar cabecera
        self.status.configure(
            text=f"{n} fila(s) copiada(s) al portapapeles.", foreground=_COLOR_OK
        )

    def _copy_selection(self) -> None:
        rows = self._get_rows_for_copy(selected_only=True)
        self._copy_to_clipboard(rows)

    def _copy_all(self) -> None:
        rows = self._get_rows_for_copy(selected_only=False)
        self._copy_to_clipboard(rows)

    # -- exportación Excel ----------------------------------------------------
    def _export_excel(self) -> None:
        if not self.data:
            messagebox.showinfo(
                "Sin datos", "No hay datos para exportar. Realiza primero una consulta."
            )
            return

        default_name = f"tipo_cambio_sunat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename = filedialog.asksaveasfilename(
            title="Guardar archivo Excel",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel (*.xlsx)", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if not filename:
            return

        # T3.6: lazy import — `import app` must not load openpyxl. The
        # XLSX-only path is the only one paying the cost. El armado y
        # estilo del workbook vive en core.excel.write_xlsx (compartido
        # con el CLI).
        from core.excel import write_xlsx

        try:
            write_xlsx(self.data, filename)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error al exportar", f"No se pudo guardar el archivo:\n{exc}")
            return

        self.status.configure(text=f"Exportado a {filename}", foreground=_COLOR_OK)
        msg = f"Archivo guardado en:\n{filename}\n\n¿Abrir la carpeta?"
        if messagebox.askyesno("Exportación completa", msg):
            folder = os.path.dirname(filename) or "."
            self._abrir_carpeta(folder)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Si recibe argumentos de línea de comandos, despacha al modo CLI.
    Si no, abre la GUI.
    """
    if len(sys.argv) > 1:
        from cli import run
        sys.exit(run(sys.argv[1:]))
    setup_logging()
    root = tk.Tk()
    SunatTCApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
