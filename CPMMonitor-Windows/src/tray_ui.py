import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional
import datetime

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

APP_NAME   = "SumarteRed Monitor"
BRAND_COLOR = "#FF6B35"   # naranja SumarteRed
BG_DARK    = "#1A1A2E"
BG_CARD    = "#16213E"
BG_ROW_ALT = "#0F3460"
TEXT_WHITE  = "#FFFFFF"
TEXT_LABEL  = "#A0A0B0"
GREEN       = "#4CAF50"
YELLOW      = "#FFC107"

# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

def make_icon(active: bool) -> Image.Image:
    img  = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (255, 107, 53, 255) if active else (128, 128, 128, 255)
    draw.ellipse([4, 4, 60, 60], fill=color)
    # inner dot for "recording" feel
    if active:
        draw.ellipse([24, 24, 40, 40], fill=(255, 255, 255, 200))
    return img


# ---------------------------------------------------------------------------
# Monitor Window
# ---------------------------------------------------------------------------

class MonitorWindow:
    """Ventana principal de monitoreo con historial de plays."""

    def __init__(self, config, scanner, db) -> None:
        self._config  = config
        self._scanner = scanner
        self._db      = db
        self._root: Optional[tk.Toplevel] = None
        self._refresh_job = None
        self._lock = threading.Lock()

    def show(self) -> None:
        """Abrir (o traer al frente) la ventana de monitoreo."""
        t = threading.Thread(target=self._run_window, daemon=True, name='MonitorWindow')
        t.start()

    def _run_window(self) -> None:
        with self._lock:
            if self._root is not None:
                try:
                    self._root.lift()
                    self._root.focus_force()
                    return
                except Exception:
                    self._root = None

        root = tk.Tk()
        self._root = root
        root.title(APP_NAME)
        root.geometry("680x520")
        root.minsize(580, 420)
        root.configure(bg=BG_DARK)
        root.attributes('-topmost', False)

        # ── Header ──────────────────────────────────────────────────────────
        header = tk.Frame(root, bg=BRAND_COLOR, height=48)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="● SumarteRed Monitor",
                 bg=BRAND_COLOR, fg=TEXT_WHITE,
                 font=('Segoe UI', 13, 'bold')).pack(side='left', padx=16, pady=10)

        self._rms_lbl = tk.Label(header, text="", bg=BRAND_COLOR, fg=TEXT_WHITE,
                                  font=('Segoe UI', 9))
        self._rms_lbl.pack(side='right', padx=8)

        self._status_lbl = tk.Label(header, text="", bg=BRAND_COLOR, fg=TEXT_WHITE,
                                     font=('Segoe UI', 10))
        self._status_lbl.pack(side='right', padx=16)

        # ── Now playing card ─────────────────────────────────────────────────
        card = tk.Frame(root, bg=BG_CARD, pady=10, padx=16)
        card.pack(fill='x', padx=10, pady=(10, 0))

        tk.Label(card, text="ESCUCHANDO AHORA", bg=BG_CARD, fg=BRAND_COLOR,
                 font=('Segoe UI', 8, 'bold')).grid(row=0, column=0, sticky='w')

        self._now_title  = tk.Label(card, text="—", bg=BG_CARD, fg=TEXT_WHITE,
                                     font=('Segoe UI', 14, 'bold'))
        self._now_title.grid(row=1, column=0, sticky='w')

        self._now_sub    = tk.Label(card, text="", bg=BG_CARD, fg=TEXT_LABEL,
                                     font=('Segoe UI', 10))
        self._now_sub.grid(row=2, column=0, sticky='w')

        self._now_pct    = tk.Label(card, text="", bg=BG_CARD, fg=GREEN,
                                     font=('Segoe UI', 10, 'bold'))
        self._now_pct.grid(row=1, column=1, rowspan=2, padx=(20, 0), sticky='e')

        card.columnconfigure(0, weight=1)

        # ── Progress bar ─────────────────────────────────────────────────────
        self._progress = ttk.Progressbar(root, orient='horizontal', mode='determinate')
        self._progress.pack(fill='x', padx=10, pady=(4, 0))

        style = ttk.Style()
        style.theme_use('default')
        style.configure("green.Horizontal.TProgressbar", troughcolor=BG_CARD,
                        background=GREEN, bordercolor=BG_CARD, lightcolor=GREEN, darkcolor=GREEN)
        self._progress.configure(style="green.Horizontal.TProgressbar")

        # ── Stats strip ──────────────────────────────────────────────────────
        stats_frame = tk.Frame(root, bg=BG_DARK)
        stats_frame.pack(fill='x', padx=10, pady=(8, 0))

        self._stat_today  = self._stat_box(stats_frame, "HOY",        "—")
        self._stat_pagan  = self._stat_box(stats_frame, "PAGAN",      "—")
        self._stat_pend   = self._stat_box(stats_frame, "PENDIENTES", "—")

        for i in range(3):
            stats_frame.columnconfigure(i, weight=1)

        # ── Notebook: Historial + Promovidas ─────────────────────────────────
        style.configure("TNotebook",            background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab",        background=BG_CARD, foreground=TEXT_LABEL,
                        font=('Segoe UI', 9, 'bold'), padding=[12, 4])
        style.map("TNotebook.Tab",
                  background=[('selected', BRAND_COLOR)],
                  foreground=[('selected', TEXT_WHITE)])

        nb = ttk.Notebook(root)
        nb.pack(fill='both', expand=True, padx=10, pady=(8, 10))

        # ── Tab 1: Historial ─────────────────────────────────────────────────
        hist_frame = tk.Frame(nb, bg=BG_DARK)
        nb.add(hist_frame, text='  Historial  ')

        cols = ('hora', 'cancion', 'pct', 'estado')
        self._tree = ttk.Treeview(hist_frame, columns=cols, show='headings', selectmode='none')

        style.configure("Treeview",
                        background=BG_CARD, foreground=TEXT_WHITE,
                        fieldbackground=BG_CARD, rowheight=26,
                        font=('Segoe UI', 9))
        style.configure("Treeview.Heading",
                        background=BG_DARK, foreground=TEXT_LABEL,
                        font=('Segoe UI', 9, 'bold'))
        style.map("Treeview", background=[('selected', BG_ROW_ALT)])

        self._tree.heading('hora',    text='Hora')
        self._tree.heading('cancion', text='Canción')
        self._tree.heading('pct',     text='%')
        self._tree.heading('estado',  text='Estado')

        self._tree.column('hora',    width=55,  stretch=False, anchor='center')
        self._tree.column('cancion', width=360, stretch=True)
        self._tree.column('pct',     width=55,  stretch=False, anchor='center')
        self._tree.column('estado',  width=120, stretch=False, anchor='center')

        sb1 = ttk.Scrollbar(hist_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb1.set)
        self._tree.pack(side='left', fill='both', expand=True)
        sb1.pack(side='right', fill='y')

        self._tree.tag_configure('paga',    foreground=GREEN)
        self._tree.tag_configure('catalog', foreground=YELLOW)
        self._tree.tag_configure('normal',  foreground=TEXT_LABEL)

        # ── Tab 2: Promovidas ────────────────────────────────────────────────
        prom_frame = tk.Frame(nb, bg=BG_DARK)
        nb.add(prom_frame, text='  ⭐ Promovidas  ')

        # Banner de conteo
        prom_top = tk.Frame(prom_frame, bg=BG_CARD, pady=8, padx=16)
        prom_top.pack(fill='x')
        tk.Label(prom_top, text="⭐  PROMOVIDAS DETECTADAS HOY",
                 bg=BG_CARD, fg=BRAND_COLOR,
                 font=('Segoe UI', 9, 'bold')).pack(side='left')
        self._prom_count_lbl = tk.Label(prom_top, text="0",
                                         bg=BG_CARD, fg=TEXT_WHITE,
                                         font=('Segoe UI', 14, 'bold'))
        self._prom_count_lbl.pack(side='right', padx=8)

        pcols = ('hora', 'cancion', 'pct')
        self._prom_tree = ttk.Treeview(prom_frame, columns=pcols, show='headings', selectmode='none')
        self._prom_tree.heading('hora',    text='Hora')
        self._prom_tree.heading('cancion', text='Canción')
        self._prom_tree.heading('pct',     text='%')
        self._prom_tree.column('hora',    width=60,  stretch=False, anchor='center')
        self._prom_tree.column('cancion', width=420, stretch=True)
        self._prom_tree.column('pct',     width=60,  stretch=False, anchor='center')

        sb2 = ttk.Scrollbar(prom_frame, orient='vertical', command=self._prom_tree.yview)
        self._prom_tree.configure(yscrollcommand=sb2.set)
        self._prom_tree.pack(side='left', fill='both', expand=True)
        sb2.pack(side='right', fill='y')

        self._prom_tree.tag_configure('prom', foreground=YELLOW)

        # ── Initial refresh ──────────────────────────────────────────────────
        self._do_refresh(root)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
        with self._lock:
            self._root = None

    # ── Stat box helper ───────────────────────────────────────────────────────
    def _stat_box(self, parent, label, value):
        frame = tk.Frame(parent, bg=BG_CARD, pady=8, padx=12)
        frame.grid(row=0, column=len(parent.winfo_children()) - 1, sticky='ew', padx=4)
        tk.Label(frame, text=label, bg=BG_CARD, fg=TEXT_LABEL,
                 font=('Segoe UI', 7, 'bold')).pack()
        lbl = tk.Label(frame, text=value, bg=BG_CARD, fg=TEXT_WHITE,
                       font=('Segoe UI', 16, 'bold'))
        lbl.pack()
        return lbl

    # ── Periodic refresh ──────────────────────────────────────────────────────
    def _do_refresh(self, root: tk.Tk) -> None:
        try:
            self._refresh_ui(root)
        except Exception as e:
            logger.debug(f"MonitorWindow refresh error: {e}")
        if root.winfo_exists():
            root.after(3000, self._do_refresh, root)

    def _refresh_ui(self, root: tk.Tk) -> None:
        # Status header + RMS level
        if not self._config.is_activated:
            self._status_lbl.config(text="⚠ Sin configurar", fg=YELLOW)
        elif self._scanner.is_scanning:
            self._status_lbl.config(text="● Escuchando", fg=TEXT_WHITE)
        else:
            self._status_lbl.config(text="◼ Detenido", fg=TEXT_LABEL)

        try:
            rms = self._scanner.rms_level
            bar = '█' * int(min(rms / 0.004, 1.0) * 8)
            bar_text = f"🎙 {bar:<8} {rms:.4f}"
            rms_color = GREEN if rms >= 0.004 else TEXT_LABEL
            self._rms_lbl.config(text=bar_text, fg=rms_color)
        except Exception:
            pass

        # Now playing
        candidate = self._scanner.current_candidate
        if candidate:
            self._now_title.config(text=candidate.get('titulo', '—'))
            prom_badge = " ⭐" if candidate.get('is_promovida') else ""
            self._now_sub.config(text=candidate.get('artista', '') + prom_badge)
            pct = candidate.get('porcentaje', 0.0)
            self._now_pct.config(text=f"{pct:.0f}%")
            self._progress['value'] = min(pct, 100)
            color = GREEN if pct >= 80 else BRAND_COLOR
            self._now_pct.config(fg=color)
        else:
            self._now_title.config(text="—")
            self._now_sub.config(text="Esperando audio…" if self._scanner.is_scanning else "")
            self._now_pct.config(text="")
            self._progress['value'] = 0

        # Stats
        plays = []
        try:
            plays = self._db.fetch_history(limit=200)
            today = datetime.date.today()
            today_plays   = [p for p in plays if _play_date(p) == today]
            today_total   = len(today_plays)
            today_pagan   = sum(1 for p in today_plays if p.get('porcentaje', 0) >= 80 and p.get('in_catalog'))
            pending       = self._db.count_pending()
            self._stat_today.config(text=str(today_total))
            self._stat_pagan.config(text=str(today_pagan))
            self._stat_pend.config(text=str(pending))
        except Exception:
            plays = []

        # History table
        self._tree.delete(*self._tree.get_children())
        for p in plays[:50]:
            hora    = _play_hora(p)
            cancion = f"{p.get('artista','')} — {p.get('titulo','')}"
            pct     = f"{p.get('porcentaje', 0):.0f}%"
            paga    = p.get('in_catalog') and p.get('porcentaje', 0) >= 80
            cat     = p.get('in_catalog') and not paga
            if paga:
                estado = "✅ Pagada"
                tag    = 'paga'
            elif cat:
                estado = "⭐ Catálogo"
                tag    = 'catalog'
            else:
                estado = "○ No paga"
                tag    = 'normal'
            self._tree.insert('', 'end', values=(hora, cancion, pct, estado), tags=(tag,))

        # Promovidas table
        try:
            today = datetime.date.today()
            promovidas = [p for p in plays if p.get('is_promovida') and _play_date(p) == today]
            self._prom_count_lbl.config(text=str(len(promovidas)))
            self._prom_tree.delete(*self._prom_tree.get_children())
            for p in promovidas:
                hora    = _play_hora(p)
                cancion = f"⭐ {p.get('artista','')} — {p.get('titulo','')}"
                pct     = f"{p.get('porcentaje', 0):.0f}%"
                self._prom_tree.insert('', 'end', values=(hora, cancion, pct), tags=('prom',))
        except Exception:
            pass


def _play_date(play: dict) -> datetime.date:
    try:
        return datetime.datetime.fromtimestamp(play.get('created_at', 0)).date()
    except Exception:
        return datetime.date.min

def _play_hora(play: dict) -> str:
    try:
        return datetime.datetime.fromtimestamp(play.get('created_at', 0)).strftime('%H:%M')
    except Exception:
        return '--:--'


# ---------------------------------------------------------------------------
# Config dialog
# ---------------------------------------------------------------------------

class ConfigDialog:
    def __init__(self, config) -> None:
        self._config = config
        self._root: Optional[tk.Tk] = None

    def show(self) -> None:
        t = threading.Thread(target=self._run_dialog, daemon=True, name='ConfigDialog')
        t.start()

    def _run_dialog(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title(f"{APP_NAME} - Config")
        root.resizable(False, False)
        root.attributes('-topmost', True)
        root.configure(bg='#f0f0f0')

        pad = {'padx': 10, 'pady': 6}

        tk.Label(root, text="Venue ID:").grid(row=0, column=0, sticky='w', **pad)
        venue_var = tk.StringVar(value=self._config.venue_id)
        tk.Entry(root, textvariable=venue_var, width=38).grid(row=0, column=1, **pad)

        tk.Label(root, text="API Key:").grid(row=1, column=0, sticky='w', **pad)
        api_key_var = tk.StringVar(value=self._config.api_key)
        api_entry = tk.Entry(root, textvariable=api_key_var, width=38, show='*')
        api_entry.grid(row=1, column=1, **pad)

        show_var = tk.BooleanVar()
        def toggle_show():
            api_entry.config(show='' if show_var.get() else '*')
        tk.Checkbutton(root, text="Mostrar API Key", variable=show_var,
                       command=toggle_show).grid(row=2, column=1, sticky='w', padx=10)

        tk.Label(root, text="Servidor URL:").grid(row=3, column=0, sticky='w', **pad)
        server_var = tk.StringVar(value=self._config.server_url)
        tk.Entry(root, textvariable=server_var, width=38).grid(row=3, column=1, **pad)

        status_var = tk.StringVar()
        status_lbl = tk.Label(root, textvariable=status_var, fg='gray', wraplength=320)
        status_lbl.grid(row=4, column=0, columnspan=2, **pad)

        btn_frame = tk.Frame(root)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))

        def verify_and_save():
            vid  = venue_var.get().strip()
            akey = api_key_var.get().strip()
            surl = server_var.get().strip().rstrip('/')
            if not vid or not akey or not surl:
                status_var.set("Completa todos los campos.")
                status_lbl.config(fg='red')
                return
            status_var.set("Verificando...")
            status_lbl.config(fg='gray')
            root.update_idletasks()

            from src.api_client import APIClient
            class _Cfg:
                api_key    = akey
                server_url = surl
            result = APIClient(_Cfg()).verify_venue(vid, akey, surl)
            if result and result.get('ok'):
                self._config.venue_id   = vid
                self._config.api_key    = akey
                self._config.server_url = surl
                self._config.save()
                status_var.set(f"✅ Verificado: {result.get('nombre_local', vid)}")
                status_lbl.config(fg='green')
                root.after(1500, root.destroy)
            else:
                status_var.set("Error: no se pudo verificar el local. Revisa los datos.")
                status_lbl.config(fg='red')

        tk.Button(btn_frame, text="Verificar y Guardar", command=verify_and_save, width=20).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancelar", command=root.destroy, width=10).pack(side='left', padx=5)

        root.mainloop()
        self._root = None


# ---------------------------------------------------------------------------
# Tray UI
# ---------------------------------------------------------------------------

class TrayUI:
    def __init__(self, config, scanner, sync_manager, db) -> None:
        self._config   = config
        self._scanner  = scanner
        self._sync     = sync_manager
        self._db       = db
        self._icon: Optional[pystray.Icon] = None
        self._active   = False
        self._status_text = ""
        self._config_dialog  = ConfigDialog(config)
        self._monitor_window = MonitorWindow(config, scanner, db)

        scanner.on_status_change = self._on_scanner_status

    def run(self) -> None:
        self._update_status_text()
        self._icon = pystray.Icon(
            name=APP_NAME,
            icon=make_icon(self._active),
            title=self._tooltip(),
            menu=self._build_menu(),
        )
        self._icon.run()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Ver Monitoreo",   self._open_monitor, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "⏹ Detener" if self._scanner.is_scanning else "▶ Iniciar",
                self._toggle_scanning,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Configuración...", self._open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._quit),
        )

    def _open_monitor(self, icon=None, item=None) -> None:
        self._monitor_window.show()

    def _open_config(self, icon=None, item=None) -> None:
        self._config_dialog.show()

    def _toggle_scanning(self, icon, item) -> None:
        if self._scanner.is_scanning:
            self._scanner.stop()
            self._active      = False
            self._status_text = "Detenido"
        else:
            if not self._config.is_activated:
                self._status_text = "Sin configurar"
                self._active      = False
            else:
                self._scanner.start()
                self._active      = True
                self._status_text = "Escuchando..."
        self._refresh_icon()

    def _quit(self, icon, item) -> None:
        try: self._scanner.stop()
        except Exception: pass
        try: self._sync.stop()
        except Exception: pass
        icon.stop()

    def _on_scanner_status(self, status: str) -> None:
        self._status_text = status
        self._active      = self._scanner.is_scanning
        if self._icon:
            self._refresh_icon()

    def _update_status_text(self) -> None:
        if not self._config.is_activated:
            self._status_text = "Sin configurar"
            self._active      = False
        elif self._scanner.is_scanning:
            self._status_text = "Escuchando..."
            self._active      = True
        else:
            self._status_text = "Detenido"
            self._active      = False

    def _tooltip(self) -> str:
        return f"{APP_NAME} — {self._status_text}"

    def _refresh_icon(self) -> None:
        if self._icon:
            self._icon.icon  = make_icon(self._active)
            self._icon.title = self._tooltip()
