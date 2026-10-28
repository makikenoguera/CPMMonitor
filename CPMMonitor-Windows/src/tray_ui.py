"""SumarteRed Monitor — Tray UI for Windows.

Design matches the macOS app: light theme, 3-tab monitor window
(Promovidas · Monitoreo · Ganancias), custom tab bar with underline indicator.
"""

import datetime
import logging
import threading
import webbrowser
from typing import Optional

import tkinter as tk
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

APP_NAME = "SumarteRed Monitor"

# ── Light palette (mirrors SRColor in Swift) ──────────────────────────────────
BG_PAGE   = "#F7F7F8"
BG_CARD   = "#FFFFFF"
BG_HEADER = "#FFFFFF"
BORDER    = "#E5E5EA"
BRAND     = "#FF6B35"
SR_GREEN  = "#1DB954"
TEXT_MAIN = "#1A1A1A"
TEXT_SEC  = "#6B6B6B"
TEXT_LBL  = "#AEAEB2"
ORANGE    = "#FF8C42"
SPOTIFY_C = "#1DB954"
YOUTUBE_C = "#CC0000"

FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_BODY   = ("Segoe UI", 11)
FONT_SMALL  = ("Segoe UI", 9)
FONT_LABEL  = ("Segoe UI", 8, "bold")
FONT_MONO   = ("Consolas", 9)
FONT_BIG    = ("Segoe UI", 22, "bold")


# ── Tray icon ─────────────────────────────────────────────────────────────────

def make_icon(active: bool) -> Image.Image:
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (255, 107, 53, 255) if active else (150, 150, 150, 255)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=color)
    # waveform bars (simplified)
    if active:
        for x, h in [(18, 28), (26, 40), (34, 32), (42, 20), (50, 36)]:
            y0 = 32 - h // 2
            draw.rounded_rectangle([x - 3, y0, x + 3, y0 + h], radius=3,
                                   fill=(255, 255, 255, 220))
    return img


# ── Helpers ───────────────────────────────────────────────────────────────────

def _play_date(play: dict) -> datetime.date:
    try:
        return datetime.datetime.fromtimestamp(play.get("created_at", 0)).date()
    except Exception:
        return datetime.date.min


def _play_hora(play: dict) -> str:
    try:
        return datetime.datetime.fromtimestamp(play.get("created_at", 0)).strftime("%H:%M")
    except Exception:
        return "--:--"


def _start_of_month() -> datetime.datetime:
    now = datetime.datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _format_seconds(s: float) -> str:
    s = int(s)
    if s >= 60:
        return f"{s // 60}m {s % 60}s"
    return f"{s}s"


def _format_cop(amount: float) -> str:
    return f"${int(amount):,} COP".replace(",", ".")


# ── Scrollable frame helper ───────────────────────────────────────────────────

class ScrollFrame(tk.Frame):
    """A frame with a vertical scrollbar."""
    def __init__(self, parent, bg=BG_PAGE, **kw):
        super().__init__(parent, bg=bg, **kw)
        canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        vsb    = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=bg)
        self.inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        # Mouse-wheel scroll
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self._canvas = canvas

    def refresh_scroll(self):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))


# ── Monitor Window ────────────────────────────────────────────────────────────

class MonitorWindow:
    """Main monitoring window — mirrors the macOS panel UI."""

    REFRESH_MS  = 3000
    PROMO_CACHE_TTL = 300   # seconds before re-fetching promovidas

    def __init__(self, config, scanner, db) -> None:
        self._config  = config
        self._scanner = scanner
        self._db      = db

        self._root: Optional[tk.Tk] = None
        self._lock = threading.Lock()

        # Tab state
        self._active_tab  = 1      # 0=Promovidas 1=Monitoreo 2=Ganancias
        self._tab_frames: list = []
        self._tab_btns:   list = []

        # Promovidas cache
        self._promovidas:       list = []   # from server
        self._promos_loading            = False
        self._promos_last_fetch: float  = 0.0
        self._promos_error: str         = ""

        # Settings panel visible?
        self._show_settings = False

    # ── Public ────────────────────────────────────────────────────────────────

    def show(self) -> None:
        """Open or bring the window to front."""
        with self._lock:
            if self._root is not None:
                try:
                    self._root.after(0, self._root.lift)
                    self._root.after(0, self._root.focus_force)
                    return
                except Exception:
                    self._root = None
        t = threading.Thread(target=self._run, daemon=True, name="MonitorWindow")
        t.start()

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:
            logger.error("MonitorWindow crashed: %s", exc, exc_info=True)
        finally:
            with self._lock:
                self._root = None

    def _run_inner(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title(APP_NAME)
        root.geometry("580x680")
        root.minsize(520, 580)
        root.configure(bg=BG_PAGE)
        root.resizable(True, True)

        # ttk styles
        self._setup_styles(root)

        # ── Header ────────────────────────────────────────────────────────────
        self._build_header(root)
        tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

        # ── Now Playing card ──────────────────────────────────────────────────
        self._np_frame = tk.Frame(root, bg=BG_PAGE)
        self._np_frame.pack(fill="x", padx=14, pady=(12, 6))
        self._build_now_playing(self._np_frame)

        # ── Tab bar ───────────────────────────────────────────────────────────
        self._tab_bar_frame = tk.Frame(root, bg=BG_PAGE)
        self._tab_bar_frame.pack(fill="x", padx=14, pady=(4, 0))
        self._build_tab_bar(self._tab_bar_frame)
        tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

        # ── Content frames (one per tab) ──────────────────────────────────────
        self._content_host = tk.Frame(root, bg=BG_PAGE)
        self._content_host.pack(fill="both", expand=True)

        self._frame_promovidas = self._build_tab_promovidas(self._content_host)
        self._frame_monitoreo  = self._build_tab_monitoreo(self._content_host)
        self._frame_ganancias  = self._build_tab_ganancias(self._content_host)

        self._switch_tab(self._active_tab)

        # ── Kick off refresh loop ─────────────────────────────────────────────
        self._do_refresh(root)

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
        with self._lock:
            self._root = None

    def _setup_styles(self, root):
        style = ttk.Style(root)
        style.theme_use("default")
        style.configure("Treeview",
                        background=BG_CARD, foreground=TEXT_MAIN,
                        fieldbackground=BG_CARD, rowheight=30,
                        borderwidth=0, font=FONT_BODY)
        style.configure("Treeview.Heading",
                        background=BG_PAGE, foreground=TEXT_LBL,
                        font=FONT_LABEL, relief="flat")
        style.map("Treeview", background=[("selected", "#EEF2FF")])
        style.configure("TProgressbar",
                        troughcolor=BORDER, background=BRAND,
                        borderwidth=0, thickness=5)
        style.configure("green.TProgressbar",
                        troughcolor=BORDER, background=SR_GREEN,
                        borderwidth=0, thickness=5)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self, parent):
        hdr = tk.Frame(parent, bg=BG_HEADER)
        hdr.pack(fill="x")

        left = tk.Frame(hdr, bg=BG_HEADER)
        left.pack(side="left", padx=14, pady=10)

        # Orange icon square
        icon_frame = tk.Frame(left, bg=BRAND, width=30, height=30)
        icon_frame.pack(side="left")
        icon_frame.pack_propagate(False)
        tk.Label(icon_frame, text="♪", bg=BRAND, fg="white",
                 font=("Segoe UI", 13, "bold")).place(relx=0.5, rely=0.5, anchor="center")

        title_f = tk.Frame(left, bg=BG_HEADER)
        title_f.pack(side="left", padx=(8, 0))
        tk.Label(title_f, text=APP_NAME, bg=BG_HEADER, fg=TEXT_MAIN,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self._venue_lbl = tk.Label(title_f, text="", bg=BG_HEADER, fg=TEXT_LBL,
                                    font=FONT_SMALL)
        self._venue_lbl.pack(anchor="w")

        right = tk.Frame(hdr, bg=BG_HEADER)
        right.pack(side="right", padx=14, pady=10)

        # Settings button
        tk.Button(right, text="⚙", bg=BG_HEADER, fg=TEXT_SEC,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 13),
                  command=self._toggle_settings).pack(side="right", padx=(6, 0))

        # Sync button
        tk.Button(right, text="↺", bg=BG_HEADER, fg=BRAND,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 14, "bold"),
                  command=self._manual_sync).pack(side="right", padx=(0, 2))

        # Sync badge
        self._sync_badge = tk.Label(right, text="✓ Sincronizado",
                                     bg=BG_HEADER, fg=SR_GREEN, font=FONT_SMALL)
        self._sync_badge.pack(side="right", padx=(0, 8))

    # ── Now Playing ───────────────────────────────────────────────────────────

    def _build_now_playing(self, parent):
        """Build the now-playing card widgets inside parent."""
        # Card with rounded border simulation
        self._np_card = tk.Frame(parent, bg=BG_CARD, bd=1, relief="solid",
                                  highlightbackground=BORDER, highlightthickness=1)
        self._np_card.pack(fill="x")

        # Orange top accent (hidden when idle)
        self._np_accent = tk.Frame(self._np_card, bg=BRAND, height=2)
        self._np_accent.pack(fill="x")

        inner = tk.Frame(self._np_card, bg=BG_CARD)
        inner.pack(fill="x", padx=14, pady=10)

        # Row 1: label + badge
        row1 = tk.Frame(inner, bg=BG_CARD)
        row1.pack(fill="x")
        self._np_label_lbl = tk.Label(row1, text="REPRODUCIENDO AHORA",
                                       bg=BG_CARD, fg=TEXT_LBL, font=FONT_LABEL)
        self._np_label_lbl.pack(side="left")
        self._np_badge = tk.Label(row1, text="", bg=BG_CARD, fg=BRAND, font=FONT_SMALL)
        self._np_badge.pack(side="right")

        # Row 2: title + %
        row2 = tk.Frame(inner, bg=BG_CARD)
        row2.pack(fill="x", pady=(4, 0))
        self._np_title = tk.Label(row2, text="Sin reproducción activa",
                                   bg=BG_CARD, fg=TEXT_SEC,
                                   font=("Segoe UI", 12))
        self._np_title.pack(side="left")
        self._np_pct = tk.Label(row2, text="", bg=BG_CARD, fg=BRAND, font=FONT_BIG)
        self._np_pct.pack(side="right")

        # Row 3: artist/status + seconds
        row3 = tk.Frame(inner, bg=BG_CARD)
        row3.pack(fill="x", pady=(2, 0))
        self._np_artist = tk.Label(row3, text="Esperando audio del sistema…",
                                    bg=BG_CARD, fg=TEXT_LBL, font=FONT_SMALL)
        self._np_artist.pack(side="left")
        self._np_seconds = tk.Label(row3, text="", bg=BG_CARD, fg=TEXT_LBL, font=FONT_SMALL)
        self._np_seconds.pack(side="right")

        # Progress bar
        self._np_progress = ttk.Progressbar(inner, orient="horizontal",
                                             mode="determinate", length=200)
        self._np_progress.pack(fill="x", pady=(6, 0))

    # ── Tab bar ───────────────────────────────────────────────────────────────

    def _build_tab_bar(self, parent):
        tabs = [("☆  Promovidas", 0), ("♪  Monitoreo", 1), ("$  Ganancias", 2)]
        self._tab_btns = []
        for label, idx in tabs:
            col = tk.Frame(parent, bg=BG_PAGE)
            col.pack(side="left", expand=True, fill="x")

            btn = tk.Button(col, text=label, bg=BG_PAGE, fg=TEXT_SEC,
                            relief="flat", bd=0, cursor="hand2",
                            font=("Segoe UI", 11),
                            command=lambda i=idx: self._switch_tab(i))
            btn.pack(fill="x", padx=4, pady=(4, 0))

            underline = tk.Frame(col, bg=BG_PAGE, height=2)
            underline.pack(fill="x")

            self._tab_btns.append((btn, underline))

    def _switch_tab(self, idx: int) -> None:
        self._active_tab = idx
        frames = [self._frame_promovidas, self._frame_monitoreo, self._frame_ganancias]
        for i, f in enumerate(frames):
            if i == idx:
                f.pack(fill="both", expand=True)
            else:
                f.pack_forget()

        for i, (btn, ul) in enumerate(self._tab_btns):
            if i == idx:
                btn.config(fg=BRAND, font=("Segoe UI", 11, "bold"))
                ul.config(bg=BRAND)
            else:
                btn.config(fg=TEXT_SEC, font=("Segoe UI", 11))
                ul.config(bg=BG_PAGE)

        # Lazy-load promovidas when switching to that tab
        if idx == 0:
            self._maybe_fetch_promovidas()

    # ── Tab: Promovidas ───────────────────────────────────────────────────────

    def _build_tab_promovidas(self, parent) -> tk.Frame:
        f = tk.Frame(parent, bg=BG_PAGE)

        # Banner row
        banner = tk.Frame(f, bg=BG_PAGE)
        banner.pack(fill="x", padx=14, pady=(8, 4))
        self._promo_count_lbl = tk.Label(banner, text="", bg=BG_PAGE, fg=BRAND,
                                          font=("Segoe UI", 9, "bold"))
        self._promo_count_lbl.pack(side="left")
        tk.Button(banner, text="↺", bg=BG_PAGE, fg=TEXT_LBL,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 12),
                  command=self._fetch_promovidas_now).pack(side="right")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", padx=14)

        # Scrollable list area
        self._promo_scroll = ScrollFrame(f, bg=BG_PAGE)
        self._promo_scroll.pack(fill="both", expand=True)

        # Status label (loading / error / empty)
        self._promo_status = tk.Label(self._promo_scroll.inner, text="Cargando…",
                                       bg=BG_PAGE, fg=TEXT_LBL, font=FONT_BODY)
        self._promo_status.pack(pady=40)

        return f

    def _maybe_fetch_promovidas(self):
        import time
        if (not self._promos_loading
                and time.time() - self._promos_last_fetch > self.PROMO_CACHE_TTL):
            self._fetch_promovidas_now()

    def _fetch_promovidas_now(self):
        if self._promos_loading:
            return
        self._promos_loading = True
        self._promos_error = ""
        if self._root:
            self._root.after(0, lambda: self._promo_status.config(
                text="Cargando promovidas…", fg=TEXT_LBL))
        t = threading.Thread(target=self._fetch_promovidas_bg, daemon=True)
        t.start()

    def _fetch_promovidas_bg(self):
        import time
        import requests
        try:
            url  = f"{self._config.server_url}/v1/promovidas"
            hdrs = {"X-API-Key": self._config.api_key}
            resp = requests.get(url, headers=hdrs, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self._promovidas     = [r for r in data if r.get("activa")]
            self._promos_error   = ""
            self._promos_last_fetch = time.time()
        except Exception as e:
            self._promos_error = str(e)
            logger.warning("Promovidas fetch error: %s", e)
        finally:
            self._promos_loading = False
            if self._root:
                self._root.after(0, self._render_promovidas)

    def _render_promovidas(self):
        inner = self._promo_scroll.inner
        for w in inner.winfo_children():
            w.destroy()

        if self._promos_error and not self._promovidas:
            tk.Label(inner, text="⚠ No se pudo cargar", bg=BG_PAGE,
                     fg=ORANGE, font=FONT_BODY).pack(pady=10)
            tk.Label(inner, text=self._promos_error, bg=BG_PAGE,
                     fg=TEXT_LBL, font=FONT_SMALL, wraplength=400).pack()
            tk.Button(inner, text="Reintentar", bg=BG_PAGE, fg=BRAND,
                      relief="flat", cursor="hand2",
                      command=self._fetch_promovidas_now).pack(pady=8)
            self._promo_count_lbl.config(text="")
            return

        if not self._promovidas:
            tk.Label(inner, text="☆", bg=BG_PAGE, fg=TEXT_LBL,
                     font=("Segoe UI", 28)).pack(pady=(30, 4))
            tk.Label(inner, text="Sin canciones promovidas",
                     bg=BG_PAGE, fg=TEXT_SEC, font=FONT_BODY).pack()
            tk.Label(inner, text="Agrega canciones en:\nmonitor.sumartered.com",
                     bg=BG_PAGE, fg=TEXT_LBL, font=FONT_SMALL,
                     justify="center").pack(pady=4)
            self._promo_count_lbl.config(text="")
            return

        self._promo_count_lbl.config(
            text=f"★  {len(self._promovidas)} canciones promovidas activas")

        for i, row in enumerate(self._promovidas):
            self._promo_row(inner, row)
            if i < len(self._promovidas) - 1:
                tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=14)

        self._promo_scroll.refresh_scroll()

    def _promo_row(self, parent, row: dict):
        f = tk.Frame(parent, bg=BG_CARD)
        f.pack(fill="x", padx=0)

        inner = tk.Frame(f, bg=BG_CARD)
        inner.pack(fill="x", padx=14, pady=10)

        # Music note circle
        icon_frame = tk.Frame(inner, bg=BRAND, width=34, height=34)
        icon_frame.pack(side="left")
        icon_frame.pack_propagate(False)
        tk.Label(icon_frame, text="♪", bg=BRAND, fg="white",
                 font=("Segoe UI", 13, "bold")).place(relx=0.5, rely=0.5, anchor="center")

        # Text block
        txt = tk.Frame(inner, bg=BG_CARD)
        txt.pack(side="left", fill="x", expand=True, padx=(10, 0))

        titulo   = row.get("titulo", "—")
        artista  = row.get("artista_nombre", "")
        isrc     = row.get("isrc", "")
        genero   = row.get("genero", "")

        tk.Label(txt, text=titulo, bg=BG_CARD, fg=TEXT_MAIN,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")

        sub_parts = [artista]
        if isrc:   sub_parts.append(f"· {isrc}")
        if genero: sub_parts.append(f"· {genero}")
        tk.Label(txt, text="  ".join(p for p in sub_parts if p),
                 bg=BG_CARD, fg=TEXT_LBL, font=FONT_SMALL, anchor="w").pack(fill="x")

        # Spotify / YT badges
        badges = tk.Frame(inner, bg=BG_CARD)
        badges.pack(side="right", padx=(8, 0))

        spotify_url  = row.get("link_spotify", "")
        youtube_url  = row.get("link_youtube", "")

        if spotify_url:
            btn = tk.Button(badges, text="Spotify",
                            bg="#E8F5E9", fg=SPOTIFY_C,
                            font=("Segoe UI", 9, "bold"),
                            relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
                            command=lambda u=spotify_url: webbrowser.open(u))
            btn.pack(side="left", padx=(0, 4))

        if youtube_url:
            btn = tk.Button(badges, text="YT",
                            bg="#FFEBEE", fg=YOUTUBE_C,
                            font=("Segoe UI", 9, "bold"),
                            relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
                            command=lambda u=youtube_url: webbrowser.open(u))
            btn.pack(side="left")

    # ── Tab: Monitoreo ────────────────────────────────────────────────────────

    def _build_tab_monitoreo(self, parent) -> tk.Frame:
        f = tk.Frame(parent, bg=BG_PAGE)

        # Summary bar (updated on refresh)
        self._mon_summary = tk.Label(f, text="", bg=BG_PAGE, fg=TEXT_SEC,
                                      font=FONT_SMALL, anchor="w")
        self._mon_summary.pack(fill="x", padx=14, pady=(8, 4))
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x")

        # Scrollable history rows
        self._mon_scroll = ScrollFrame(f, bg=BG_PAGE)
        self._mon_scroll.pack(fill="both", expand=True)

        self._mon_empty = tk.Label(self._mon_scroll.inner,
                                    text="Sin reproducciones registradas",
                                    bg=BG_PAGE, fg=TEXT_LBL, font=FONT_BODY)
        self._mon_empty.pack(pady=40)
        return f

    def _render_monitoreo(self, plays: list):
        inner = self._mon_scroll.inner
        for w in inner.winfo_children():
            w.destroy()

        if not plays:
            tk.Label(inner, text="♪", bg=BG_PAGE, fg=TEXT_LBL,
                     font=("Segoe UI", 28)).pack(pady=(30, 4))
            tk.Label(inner, text="Sin reproducciones registradas",
                     bg=BG_PAGE, fg=TEXT_LBL, font=FONT_BODY).pack()
            return

        today       = datetime.date.today()
        pagadas     = sum(1 for p in plays if p.get("in_catalog") and p.get("porcentaje", 0) >= 80)
        promovidas  = sum(1 for p in plays if p.get("in_catalog"))
        otras       = len(plays) - promovidas

        parts = []
        if pagadas:   parts.append(f"★ {pagadas} pagadas")
        if promovidas: parts.append(f"{promovidas} promovidas")
        if otras:      parts.append(f"{otras} otras")
        parts.append(f"{len(plays)} total")
        self._mon_summary.config(text="  ·  ".join(parts))

        for i, p in enumerate(plays[:100]):
            self._mon_row(inner, p)
            tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=14)

        self._mon_scroll.refresh_scroll()

    def _mon_row(self, parent, p: dict):
        qualifying = bool(p.get("in_catalog")) and p.get("porcentaje", 0) >= 80
        in_cat     = bool(p.get("in_catalog"))

        bg = "#F0FFF4" if qualifying else ("#FFF8F5" if in_cat else BG_CARD)

        outer = tk.Frame(parent, bg=bg)
        outer.pack(fill="x")

        inner = tk.Frame(outer, bg=bg)
        inner.pack(fill="x", padx=14, pady=8)

        # Line 1
        row1 = tk.Frame(inner, bg=bg)
        row1.pack(fill="x")

        hora = _play_hora(p)
        tk.Label(row1, text=hora, bg=bg, fg=TEXT_LBL,
                 font=FONT_MONO, width=5).pack(side="left")

        # Fuente badge
        fuente = p.get("fuente", "local_match")
        badge_txt = "Local"
        badge_fg  = "#6C3FE8"
        badge_bg  = "#EDE8FF"
        if "spotify" in fuente.lower():
            badge_txt, badge_fg, badge_bg = "Spotify", SPOTIFY_C, "#E8F5E9"
        elif "youtube" in fuente.lower():
            badge_txt, badge_fg, badge_bg = "YouTube", YOUTUBE_C, "#FFEBEE"

        tk.Label(row1, text=badge_txt, bg=badge_bg, fg=badge_fg,
                 font=("Segoe UI", 8, "bold"), padx=5, pady=1).pack(side="left", padx=4)

        if in_cat:
            star_color = SR_GREEN if qualifying else BRAND
            tk.Label(row1, text="★", bg=bg, fg=star_color,
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))

        titulo = p.get("titulo") or p.get("contenido", "—")
        tk.Label(row1, text=titulo, bg=bg, fg=TEXT_MAIN,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", fill="x", expand=True)

        pct = p.get("porcentaje", 0)
        pct_color = SR_GREEN if qualifying else (ORANGE if pct >= 50 else TEXT_LBL)
        tk.Label(row1, text=f"{pct:.0f}%", bg=bg, fg=pct_color,
                 font=("Segoe UI", 11, "bold")).pack(side="right")

        # Status icon
        if qualifying:
            status_txt   = "✓" if p.get("synced") else "⏳"
            status_color = SR_GREEN if p.get("synced") else ORANGE
        elif in_cat:
            status_txt, status_color = "⭐", BRAND
        else:
            status_txt, status_color = "—", TEXT_LBL
        tk.Label(row1, text=status_txt, bg=bg, fg=status_color,
                 font=("Segoe UI", 10)).pack(side="right", padx=4)

        # Line 2: artist · isrc · status label · duración · tiempo
        row2 = tk.Frame(inner, bg=bg)
        row2.pack(fill="x", pady=(2, 0))

        artista = p.get("artista", "")
        isrc    = p.get("isrc", "")
        sub     = artista
        if isrc:
            sub += f"  ·  {isrc}"
        if qualifying:
            sub += "  ·  pagada"
        elif in_cat:
            sub += "  ·  promovida"
        else:
            sub += "  ·  no promovida"

        tk.Label(row2, text=sub, bg=bg, fg=TEXT_LBL,
                 font=FONT_SMALL, anchor="w").pack(side="left")

        dur_secs = p.get("segundos_escuchados", 0)
        if dur_secs:
            tk.Label(row2, text=_format_seconds(dur_secs), bg=bg, fg=TEXT_LBL,
                     font=FONT_SMALL).pack(side="right", padx=4)

    # ── Tab: Ganancias ────────────────────────────────────────────────────────

    def _build_tab_ganancias(self, parent) -> tk.Frame:
        f = tk.Frame(parent, bg=BG_PAGE)

        # Period selector
        period_f = tk.Frame(f, bg=BG_PAGE)
        period_f.pack(fill="x", padx=14, pady=(10, 6))
        self._period_lbl = tk.Label(period_f, text="Este mes", bg=BG_PAGE,
                                     fg=TEXT_LBL, font=FONT_SMALL)
        self._period_lbl.pack(side="right")
        tk.Label(period_f, text="GANANCIAS", bg=BG_PAGE, fg=TEXT_LBL,
                 font=FONT_LABEL).pack(side="left")

        # Metric cards row
        cards_f = tk.Frame(f, bg=BG_PAGE)
        cards_f.pack(fill="x", padx=14, pady=(0, 8))
        cards_f.columnconfigure(0, weight=1)
        cards_f.columnconfigure(1, weight=1)

        self._gan_plays_val = self._metric_card(cards_f, "REPRODUCCIONES PROMOVIDAS",
                                                  "0", BRAND, "★", 0)
        self._gan_income_val = self._metric_card(cards_f, "TU INGRESO",
                                                   "$0 COP", ORANGE, "$", 1)

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", padx=14)

        # Table
        self._gan_scroll = ScrollFrame(f, bg=BG_PAGE)
        self._gan_scroll.pack(fill="both", expand=True)

        # Table header
        hdr = tk.Frame(self._gan_scroll.inner, bg=BG_PAGE)
        hdr.pack(fill="x", padx=14, pady=(4, 2))
        for txt, w in [("CANCIÓN", 0), ("SONÓ", 60), ("ÚLTIMA VEZ", 90), ("GANANCIA", 100)]:
            anchor = "w" if w == 0 else "center" if txt != "GANANCIA" else "e"
            if w == 0:
                tk.Label(hdr, text=txt, bg=BG_PAGE, fg=TEXT_LBL,
                         font=FONT_LABEL, anchor=anchor).pack(side="left", expand=True, fill="x")
            else:
                tk.Label(hdr, text=txt, bg=BG_PAGE, fg=TEXT_LBL,
                         font=FONT_LABEL, width=w // 7, anchor=anchor).pack(side="left")

        tk.Frame(self._gan_scroll.inner, bg=BORDER, height=1).pack(fill="x", padx=14)

        self._gan_table_host = tk.Frame(self._gan_scroll.inner, bg=BG_PAGE)
        self._gan_table_host.pack(fill="x")

        self._gan_empty = tk.Label(self._gan_scroll.inner,
                                    text="Sin reproducciones promovidas este mes",
                                    bg=BG_PAGE, fg=TEXT_LBL, font=FONT_BODY)
        self._gan_empty.pack(pady=30)
        return f

    def _metric_card(self, parent, label, value, color, icon, col) -> tk.Label:
        card = tk.Frame(parent, bg=BG_CARD, bd=1, relief="solid",
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=0, column=col, sticky="ew",
                  padx=(0, 6) if col == 0 else (6, 0), pady=4)

        tk.Frame(card, bg=color, height=2).pack(fill="x")
        inner = tk.Frame(card, bg=BG_CARD)
        inner.pack(fill="x", padx=12, pady=(6, 12))

        tk.Label(inner, text=label, bg=BG_CARD, fg=TEXT_LBL,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        val_lbl = tk.Label(inner, text=value, bg=BG_CARD, fg=color,
                            font=("Segoe UI", 22, "bold"))
        val_lbl.pack(anchor="w")
        return val_lbl

    def _render_ganancias(self, plays: list):
        if not self._promovidas:
            # Try to compute from local catalog data
            pass

        # Build promo index
        promo_by_isrc  = {}
        promo_by_title = {}
        for p in self._promovidas:
            if p.get("isrc"):
                promo_by_isrc[p["isrc"].upper()] = p
            promo_by_title[p.get("titulo", "").lower().strip()] = p

        # Group plays
        groups: dict = {}
        today_start = _start_of_month()
        for play in plays:
            if play.get("porcentaje", 0) < 80:
                continue
            # Find matching promovida
            promo = None
            isrc = play.get("isrc", "").upper()
            if isrc and isrc in promo_by_isrc:
                promo = promo_by_isrc[isrc]
            else:
                t = play.get("titulo", "").lower().strip()
                promo = promo_by_title.get(t)

            if promo is None and not play.get("is_promovida"):
                continue

            gid = isrc or f"{play.get('artista','').lower()}|{play.get('titulo','').lower()}"
            if gid not in groups:
                tarifa = promo.get("tarifa_venue", 500) if promo else 500
                groups[gid] = {
                    "titulo":  (promo or play).get("titulo", "—"),
                    "artista": (promo.get("artista_nombre") if promo else play.get("artista", "")),
                    "tarifa":  tarifa,
                    "plays":   [],
                }
            groups[gid]["plays"].append(play)

        rows = sorted(groups.values(),
                      key=lambda g: len(g["plays"]) * g["tarifa"], reverse=True)

        total_plays    = sum(len(g["plays"]) for g in rows)
        total_earnings = sum(len(g["plays"]) * g["tarifa"] for g in rows)

        self._gan_plays_val.config(text=str(total_plays))
        self._gan_income_val.config(text=_format_cop(total_earnings))

        host = self._gan_table_host
        for w in host.winfo_children():
            w.destroy()

        if not rows:
            self._gan_empty.config(text="Sin reproducciones promovidas este mes")
            self._gan_empty.pack(pady=30)
            self._gan_scroll.refresh_scroll()
            return
        else:
            self._gan_empty.pack_forget()

        for i, g in enumerate(rows):
            self._gan_row(host, g)
            tk.Frame(host, bg=BORDER, height=1).pack(fill="x", padx=14)

        # Totals row
        tot = tk.Frame(host, bg="#FFF5EE")
        tot.pack(fill="x")
        tin = tk.Frame(tot, bg="#FFF5EE")
        tin.pack(fill="x", padx=14, pady=8)
        tk.Label(tin, text="TOTAL", bg="#FFF5EE", fg=TEXT_LBL,
                 font=FONT_LABEL).pack(side="left", expand=True, fill="x", anchor="w")
        tk.Label(tin, text=str(total_plays), bg="#FFF5EE", fg=BRAND,
                 font=("Segoe UI", 13, "bold"), width=8, anchor="center").pack(side="left")
        tk.Label(tin, text=" ", bg="#FFF5EE", width=12).pack(side="left")
        tk.Label(tin, text=_format_cop(total_earnings), bg="#FFF5EE", fg=ORANGE,
                 font=("Segoe UI", 13, "bold"), anchor="e").pack(side="right")

        self._gan_scroll.refresh_scroll()

    def _gan_row(self, parent, g: dict):
        f = tk.Frame(parent, bg=BG_CARD)
        f.pack(fill="x")
        inner = tk.Frame(f, bg=BG_CARD)
        inner.pack(fill="x", padx=14, pady=8)

        txt = tk.Frame(inner, bg=BG_CARD)
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=g["titulo"], bg=BG_CARD, fg=TEXT_MAIN,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(txt, text=g["artista"], bg=BG_CARD, fg=TEXT_LBL,
                 font=FONT_SMALL, anchor="w").pack(fill="x")

        count = len(g["plays"])
        tk.Label(inner, text=str(count), bg=BG_CARD, fg=BRAND,
                 font=("Segoe UI", 16, "bold"), width=5, anchor="center").pack(side="left")

        last_play = max((p.get("created_at", 0) for p in g["plays"]), default=0)
        last_str  = datetime.datetime.fromtimestamp(last_play).strftime("%d/%m\n%H:%M") if last_play else "—"
        tk.Label(inner, text=last_str, bg=BG_CARD, fg=TEXT_LBL,
                 font=FONT_SMALL, width=10, anchor="center", justify="center").pack(side="left")

        earnings = count * g["tarifa"]
        tk.Label(inner, text=_format_cop(earnings), bg=BG_CARD, fg=ORANGE,
                 font=("Segoe UI", 11, "bold"), anchor="e").pack(side="right")

    # ── Settings overlay ──────────────────────────────────────────────────────

    def _toggle_settings(self):
        self._show_settings = not self._show_settings
        if self._show_settings:
            self._open_settings_dialog()

    def _open_settings_dialog(self):
        """Open config as a Toplevel inside the monitor window's mainloop."""
        if self._root is None:
            return
        dlg = tk.Toplevel(self._root)
        dlg.title(f"{APP_NAME} — Configuración")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(bg="#f0f0f0")
        dlg.grab_set()

        pad = {"padx": 10, "pady": 6}

        tk.Label(dlg, text="Venue ID:").grid(row=0, column=0, sticky="w", **pad)
        venue_var = tk.StringVar(value=self._config.venue_id)
        tk.Entry(dlg, textvariable=venue_var, width=38).grid(row=0, column=1, **pad)

        tk.Label(dlg, text="API Key:").grid(row=1, column=0, sticky="w", **pad)
        api_var = tk.StringVar(value=self._config.api_key)
        api_entry = tk.Entry(dlg, textvariable=api_var, width=38, show="*")
        api_entry.grid(row=1, column=1, **pad)

        show_var = tk.BooleanVar()
        def toggle_show():
            api_entry.config(show="" if show_var.get() else "*")
        tk.Checkbutton(dlg, text="Mostrar API Key", variable=show_var,
                       command=toggle_show).grid(row=2, column=1, sticky="w", padx=10)

        tk.Label(dlg, text="Servidor URL:").grid(row=3, column=0, sticky="w", **pad)
        server_var = tk.StringVar(value=self._config.server_url)
        tk.Entry(dlg, textvariable=server_var, width=38).grid(row=3, column=1, **pad)

        status_var = tk.StringVar()
        status_lbl = tk.Label(dlg, textvariable=status_var, fg="gray", wraplength=320)
        status_lbl.grid(row=4, column=0, columnspan=2, **pad)

        btn_frame = tk.Frame(dlg)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))

        def verify_and_save():
            vid  = venue_var.get().strip()
            akey = api_var.get().strip()
            surl = server_var.get().strip().rstrip("/")
            if not vid or not akey or not surl:
                status_var.set("Completa todos los campos.")
                status_lbl.config(fg="red")
                return
            status_var.set("Verificando…")
            status_lbl.config(fg="gray")
            dlg.update_idletasks()

            from src.api_client import APIClient
            class _Cfg:
                api_key    = akey
                server_url = surl
            result = APIClient(_Cfg()).verify_venue(vid, akey, surl)
            if result and result.get("ok"):
                self._config.venue_id   = vid
                self._config.api_key    = akey
                self._config.server_url = surl
                self._config.save()
                status_var.set(f"✅ Verificado: {result.get('nombre_local', vid)}")
                status_lbl.config(fg="green")
                dlg.after(1500, dlg.destroy)
            else:
                status_var.set("Error: no se pudo verificar el local. Revisa los datos.")
                status_lbl.config(fg="red")

        tk.Button(btn_frame, text="Verificar y Guardar",
                  command=verify_and_save, width=20).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancelar",
                  command=dlg.destroy, width=10).pack(side="left", padx=5)

        self._show_settings = False

    # ── Periodic refresh ──────────────────────────────────────────────────────

    def _do_refresh(self, root: tk.Tk) -> None:
        try:
            self._refresh_all(root)
        except Exception as e:
            logger.debug("MonitorWindow refresh error: %s", e)
        if root.winfo_exists():
            root.after(self.REFRESH_MS, self._do_refresh, root)

    def _refresh_all(self, root: tk.Tk) -> None:
        # Venue label
        venue = getattr(self._config, "_data", {}).get("nombre_local", "") or self._config.venue_id
        self._venue_lbl.config(text=venue or "Sin configurar")

        # Sync badge
        try:
            pending = self._db.count_pending()
            if pending > 0:
                self._sync_badge.config(text=f"↑ {pending} pendientes", fg=ORANGE)
            else:
                self._sync_badge.config(text="✓ Sincronizado", fg=SR_GREEN)
        except Exception:
            pass

        # Now playing
        self._refresh_now_playing()

        # Load DB data
        plays = []
        try:
            plays = self._db.fetch_history(limit=200)
        except Exception:
            pass

        # Render active tab
        if self._active_tab == 1:
            self._render_monitoreo(plays)
        elif self._active_tab == 2:
            self._render_ganancias(plays)

    def _refresh_now_playing(self):
        candidate = self._scanner.current_candidate
        if candidate:
            self._np_accent.config(bg=BRAND)
            self._np_label_lbl.config(text="REPRODUCIENDO AHORA", fg=TEXT_LBL)

            titulo  = candidate.get("titulo", "—")
            artista = candidate.get("artista", "")
            pct     = candidate.get("porcentaje", 0.0)
            secs    = candidate.get("segundos_acumulados", 0)
            dur     = candidate.get("duracion_seg", 0)
            is_prom = candidate.get("is_promovida", False)
            in_cat  = candidate.get("in_catalog", False)

            self._np_title.config(text=titulo, fg=TEXT_MAIN,
                                   font=("Segoe UI", 12, "bold"))
            isrc_part = f"  ·  {candidate['isrc']}" if candidate.get("isrc") else ""
            self._np_artist.config(text=artista + isrc_part, fg=TEXT_LBL)

            dur_str = f"0:{int(dur) // 60}:{int(dur) % 60:02d}" if dur else "?"
            self._np_seconds.config(
                text=f"{_format_seconds(secs)} / {dur_str}", fg=TEXT_LBL)

            pct_color = SR_GREEN if pct >= 80 else BRAND
            self._np_pct.config(text=f"{pct:.0f}%", fg=pct_color)
            self._np_progress["value"] = min(pct, 100)
            style_name = "green.TProgressbar" if pct >= 80 else "TProgressbar"
            self._np_progress.config(style=style_name)

            if is_prom:
                self._np_badge.config(text="⭐ Promovida", fg=BRAND)
            elif in_cat:
                self._np_badge.config(text="✓ En catálogo", fg=SR_GREEN)
            else:
                self._np_badge.config(text="No promovida", fg=TEXT_LBL)
        else:
            self._np_accent.config(bg=BG_CARD)
            self._np_label_lbl.config(text="", fg=TEXT_LBL)
            scanning = self._scanner.is_scanning

            # Show RMS level as mini bar
            try:
                rms = self._scanner.rms_level
                bars = int(min(rms / 0.004, 1.0) * 6)
                bar_str = "▮" * bars + "▯" * (6 - bars)
                rms_txt = f"Audio:  {bar_str}  ({rms:.4f})"
                rms_color = SR_GREEN if rms >= 0.004 else TEXT_LBL
                self._np_seconds.config(text=rms_txt, fg=rms_color)
            except Exception:
                self._np_seconds.config(text="", fg=TEXT_LBL)

            self._np_title.config(
                text="Sin reproducción activa",
                fg=TEXT_SEC, font=("Segoe UI", 12))
            self._np_artist.config(
                text="Esperando audio del sistema…" if scanning else "Detenido",
                fg=TEXT_LBL)
            self._np_pct.config(text="")
            self._np_progress["value"] = 0
            self._np_badge.config(text="")

    # ── Sync / misc ───────────────────────────────────────────────────────────

    def _manual_sync(self):
        pass  # SyncManager.syncPending() — triggered via tray callback

    def open_config_tab(self):
        """Open settings from tray menu (no monitor window required)."""
        # If monitor is open, use Toplevel; otherwise open standalone dialog
        if self._root is not None:
            self._root.after(0, self._open_settings_dialog)
        else:
            t = threading.Thread(target=self._standalone_config, daemon=True)
            t.start()

    def _standalone_config(self):
        ConfigDialog(self._config).show()


# ── Standalone Config Dialog (used when monitor window is closed) ─────────────

class ConfigDialog:
    def __init__(self, config) -> None:
        self._config = config
        self._root: Optional[tk.Tk] = None

    def show(self) -> None:
        t = threading.Thread(target=self._run, daemon=True, name="ConfigDialog")
        t.start()

    def _run(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title(f"{APP_NAME} — Configuración")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="#f0f0f0")

        pad = {"padx": 10, "pady": 6}

        tk.Label(root, text="Venue ID:").grid(row=0, column=0, sticky="w", **pad)
        venue_var = tk.StringVar(value=self._config.venue_id)
        tk.Entry(root, textvariable=venue_var, width=38).grid(row=0, column=1, **pad)

        tk.Label(root, text="API Key:").grid(row=1, column=0, sticky="w", **pad)
        api_var   = tk.StringVar(value=self._config.api_key)
        api_entry = tk.Entry(root, textvariable=api_var, width=38, show="*")
        api_entry.grid(row=1, column=1, **pad)

        show_var = tk.BooleanVar()
        def toggle_show():
            api_entry.config(show="" if show_var.get() else "*")
        tk.Checkbutton(root, text="Mostrar API Key", variable=show_var,
                       command=toggle_show).grid(row=2, column=1, sticky="w", padx=10)

        tk.Label(root, text="Servidor URL:").grid(row=3, column=0, sticky="w", **pad)
        server_var = tk.StringVar(value=self._config.server_url)
        tk.Entry(root, textvariable=server_var, width=38).grid(row=3, column=1, **pad)

        status_var = tk.StringVar()
        status_lbl = tk.Label(root, textvariable=status_var, fg="gray", wraplength=320)
        status_lbl.grid(row=4, column=0, columnspan=2, **pad)

        btn_frame = tk.Frame(root)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))

        def verify_and_save():
            vid  = venue_var.get().strip()
            akey = api_var.get().strip()
            surl = server_var.get().strip().rstrip("/")
            if not vid or not akey or not surl:
                status_var.set("Completa todos los campos.")
                status_lbl.config(fg="red")
                return
            status_var.set("Verificando…")
            status_lbl.config(fg="gray")
            root.update_idletasks()

            from src.api_client import APIClient
            class _Cfg:
                api_key    = akey
                server_url = surl
            result = APIClient(_Cfg()).verify_venue(vid, akey, surl)
            if result and result.get("ok"):
                self._config.venue_id   = vid
                self._config.api_key    = akey
                self._config.server_url = surl
                self._config.save()
                status_var.set(f"✅ Verificado: {result.get('nombre_local', vid)}")
                status_lbl.config(fg="green")
                root.after(1500, root.destroy)
            else:
                status_var.set("Error: no se pudo verificar el local. Revisa los datos.")
                status_lbl.config(fg="red")

        tk.Button(btn_frame, text="Verificar y Guardar",
                  command=verify_and_save, width=20).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancelar",
                  command=root.destroy, width=10).pack(side="left", padx=5)

        root.mainloop()
        self._root = None


# ── Tray UI ───────────────────────────────────────────────────────────────────

class TrayUI:
    def __init__(self, config, scanner, sync_manager, db) -> None:
        self._config  = config
        self._scanner = scanner
        self._sync    = sync_manager
        self._db      = db
        self._icon: Optional[pystray.Icon] = None
        self._active  = False
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
            pystray.MenuItem("Ver Monitoreo",    self._open_monitor, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "⏹ Detener" if self._scanner.is_scanning else "▶ Iniciar",
                self._toggle_scanning,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Configuración…",   self._open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir",            self._quit),
        )

    def _open_monitor(self, icon=None, item=None) -> None:
        self._monitor_window.show()

    def _open_config(self, icon=None, item=None) -> None:
        self._monitor_window.open_config_tab()

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
                self._status_text = "Escuchando…"
        self._refresh_icon()

    def _quit(self, icon, item) -> None:
        try:  self._scanner.stop()
        except Exception: pass
        try:  self._sync.stop()
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
            self._status_text = "Escuchando…"
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
