"""
CPM Tracks - Panel principal
Diseño "Quant Modern" basado en proposal-b.jsx
Acento azul CPM #0A66B7, tipografia limpia, tabla data-dense.
"""
import sys, os, time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QFrame, QSizePolicy, QLineEdit, QApplication,
)
from PyQt5.QtCore    import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtGui     import QPixmap, QIcon, QColor, QFont

from core import database, config

# ── Tokens de color (dark mode) ───────────────────────────────────────────────
BG        = "#0E1116"
PANEL     = "#161A21"
PANEL_ALT = "#11151B"
BORDER    = "#212630"
BORDER_S  = "#2D3340"
FG        = "#ECEEF2"
FG_DIM    = "#8A8F99"
FG_FAINT  = "#525762"
ROW_HOVER = "#161A21"
ACCENT    = "#0A66B7"
OK        = "#3DDC97"
WARN      = "#F5A524"
BAD       = "#F25F5C"
SPOTIFY   = "#1DB954"

STYLE = f"""
QMainWindow, QWidget {{ background: {BG}; color: {FG}; font-family: -apple-system, Arial, sans-serif; }}
QLabel {{ color: {FG}; background: transparent; }}
QFrame {{ background: transparent; }}

QTableWidget {{
    background: {BG};
    color: {FG};
    gridline-color: transparent;
    border: none;
    font-size: 12px;
    selection-background-color: {PANEL};
}}
QTableWidget::item {{ padding: 0px 12px; border-bottom: 1px solid {BORDER}; }}
QTableWidget::item:selected {{ background: {PANEL}; color: {FG}; }}
QHeaderView::section {{
    background: {PANEL};
    color: {FG_FAINT};
    font-size: 10px;
    font-weight: bold;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QScrollBar:vertical {{
    background: {PANEL};
    width: 5px;
    border-radius: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_S};
    border-radius: 2px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QLineEdit {{
    background: {BG};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QPushButton#btn-sync {{
    background: {ACCENT};
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton#btn-sync:hover {{ background: #1F7AC8; }}

QPushButton#btn-export {{
    background: transparent;
    color: {FG_DIM};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
}}
QPushButton#btn-export:hover {{ color: {FG}; border-color: {BORDER_S}; }}

QPushButton#btn-filter {{
    background: transparent;
    color: {FG_DIM};
    border: none;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: bold;
}}
QPushButton#btn-filter:hover {{ color: {FG}; background: {PANEL}; }}
QPushButton#btn-filter[active="true"] {{
    background: {PANEL};
    color: {FG};
    border: 1px solid {BORDER};
}}
"""

def _resource(name):
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(base, name)

def _font(size, bold=False, mono=False):
    f = QFont()
    if mono:
        f.setFamily("Menlo")
        f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    f.setBold(bold)
    return f

def _col(hex_color):
    return QColor(hex_color)


STYLE_LIGHT = """
QMainWindow, QWidget { background: #FAFAFB; color: #111318; font-family: -apple-system, Arial, sans-serif; }
QLabel { color: #111318; background: transparent; }
QFrame { background: transparent; }
QTableWidget { background: #FAFAFB; color: #111318; gridline-color: transparent; border: none; font-size: 12px; selection-background-color: #F4F5F7; }
QTableWidget::item { padding: 0px 12px; border-bottom: 1px solid #E4E6EB; }
QTableWidget::item:selected { background: #F4F5F7; color: #111318; }
QHeaderView::section { background: #FFFFFF; color: #9499A2; font-size: 10px; font-weight: bold; padding: 10px 12px; border: none; border-bottom: 1px solid #E4E6EB; }
QScrollBar:vertical { background: #F2F3F5; width: 5px; border-radius: 2px; }
QScrollBar::handle:vertical { background: #CFD2D9; border-radius: 2px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLineEdit { background: #FFFFFF; color: #111318; border: 1px solid #E4E6EB; border-radius: 8px; padding: 6px 12px; font-size: 12px; }
QPushButton#btn-sync { background: #0A66B7; color: #fff; border: none; border-radius: 8px; padding: 7px 16px; font-size: 12px; font-weight: bold; }
QPushButton#btn-export { background: transparent; color: #5C616B; border: 1px solid #E4E6EB; border-radius: 8px; padding: 7px 14px; font-size: 12px; }
QPushButton#btn-filter { background: transparent; color: #5C616B; border: none; border-radius: 6px; padding: 5px 12px; font-size: 11px; font-weight: bold; }
QPushButton#btn-filter[active="true"] { background: #FFFFFF; color: #111318; border: 1px solid #E4E6EB; }
"""

class KPICard(QFrame):
    def __init__(self, label, value, sub="", color=FG, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: {PANEL_ALT}; border-radius: 8px; border: 1px solid {BORDER}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        self.lbl_label = QLabel(label.upper())
        self.lbl_label.setFont(_font(9, bold=True))
        self.lbl_label.setStyleSheet(f"color: {FG_DIM}; letter-spacing: 1px;")

        self.lbl_value = QLabel(str(value))
        self.lbl_value.setFont(_font(24, bold=True, mono=True))
        self.lbl_value.setStyleSheet(f"color: {color};")

        self.lbl_sub = QLabel(str(sub))
        self.lbl_sub.setFont(_font(10))
        self.lbl_sub.setStyleSheet(f"color: {FG_FAINT};")

        layout.addWidget(self.lbl_label)
        layout.addWidget(self.lbl_value)
        if sub:
            layout.addWidget(self.lbl_sub)

    def set_value(self, v, color=None):
        self.lbl_value.setText(str(v))
        if color:
            self.lbl_value.setStyleSheet(f"color: {color};")

    def set_sub(self, s):
        self.lbl_sub.setText(str(s))


class NowPlayingCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: {PANEL_ALT}; border-radius: 8px; border: 1px solid {BORDER}; }}")
        self.setMinimumHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Icono animado
        self.icon = QLabel("♪")
        self.icon.setFont(_font(20))
        self.icon.setStyleSheet(f"color: {ACCENT};")
        self.icon.setFixedWidth(28)
        layout.addWidget(self.icon)

        vl = QVBoxLayout()
        vl.setSpacing(2)
        self.lbl_fuente = QLabel("REPRODUCIENDO")
        self.lbl_fuente.setFont(_font(9, bold=True))
        self.lbl_fuente.setStyleSheet(f"color: {FG_DIM}; letter-spacing: 1px;")

        self.lbl_titulo = QLabel("Esperando reproducción...")
        self.lbl_titulo.setFont(_font(13, bold=True))
        self.lbl_titulo.setStyleSheet(f"color: {FG};")

        vl.addWidget(self.lbl_fuente)
        vl.addWidget(self.lbl_titulo)
        layout.addLayout(vl)
        layout.addStretch()

        self.lbl_dur = QLabel("")
        self.lbl_dur.setFont(_font(11, mono=True))
        self.lbl_dur.setStyleSheet(f"color: {FG_DIM};")
        layout.addWidget(self.lbl_dur)

    def update(self, titulo, fuente, duracion=""):
        corto = titulo[:65] + "…" if len(titulo) > 65 else titulo
        self.lbl_titulo.setText(corto)
        self.lbl_fuente.setText(f"REPRODUCIENDO · {fuente.upper()}")
        self.lbl_dur.setText(duracion)


class VentanaPrincipal(QMainWindow):
    def __init__(self, bridge=None):
        super().__init__()
        cfg = config.cargar()
        self.id_local     = cfg.get("id_local", "---")
        self.nombre_local = cfg.get("nombre_local", "CPM Tracks")

        self.setWindowTitle("CPM Monitor")
        self.resize(1060, 680)
        self.setMinimumSize(820, 540)
        self.setStyleSheet(STYLE)

        icon_path = _resource("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._total_hoy = 0
        self._filter    = "all"
        self._search    = ""
        self._all_rows  = []
        self._dark_mode = True
        self._sort_col  = None
        self._sort_asc  = True

        self._build_ui()
        self._cargar_historial()

        self.timer = QTimer()
        self.timer.timeout.connect(self._refrescar)
        self.timer.start(5000)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        rl.addWidget(self._build_titlebar())
        rl.addWidget(self._build_header())
        rl.addWidget(self._build_toolbar())
        rl.addWidget(self._build_table(), 1)
        rl.addWidget(self._build_statusbar())

    def _build_titlebar(self):
        self._titlebar = QWidget()
        self._titlebar.setFixedHeight(32)
        self._titlebar.setStyleSheet(f"background: {PANEL}; border-bottom: 1px solid {BORDER};")
        layout = QHBoxLayout(self._titlebar)
        layout.setContentsMargins(13, 0, 16, 0)
        lbl = QLabel("CPM Tracks")
        lbl.setFont(_font(11))
        lbl.setStyleSheet(f"color: {FG_DIM};")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(lbl)
        layout.addStretch()
        return self._titlebar

    def _build_header(self):
        self._header = QWidget()
        self._header.setStyleSheet(f"background: {PANEL}; border-bottom: 1px solid {BORDER};")
        layout = QVBoxLayout(self._header)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.setSpacing(16)

        logo_path = _resource("logo.png")
        if os.path.exists(logo_path):
            lbl_logo = QLabel()
            lbl_logo.setPixmap(QPixmap(logo_path).scaledToHeight(26, Qt.SmoothTransformation))
            top.addWidget(lbl_logo)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {BORDER};")
        sep.setFixedWidth(1)
        top.addWidget(sep)

        vl = QVBoxLayout()
        vl.setSpacing(1)
        lbl_local_l = QLabel("Establecimiento")
        lbl_local_l.setFont(_font(9))
        lbl_local_l.setStyleSheet(f"color: {FG_DIM};")
        self.lbl_local = QLabel(self.id_local)
        self.lbl_local.setFont(_font(12, bold=True))
        vl.addWidget(lbl_local_l)
        vl.addWidget(self.lbl_local)
        top.addLayout(vl)

        badge = QLabel("● activo")
        badge.setFont(_font(10))
        badge.setStyleSheet(f"color: {OK}; background: {OK}22; border-radius: 8px; padding: 2px 8px;")
        top.addWidget(badge)
        top.addStretch()

        self.btn_theme = QPushButton("☀ Claro")
        self.btn_theme.setObjectName("btn-export")
        self.btn_theme.setFont(_font(11))
        self.btn_theme.setFixedHeight(32)
        self.btn_theme.clicked.connect(self._toggle_theme)
        top.addWidget(self.btn_theme)

        btn_export = QPushButton("⬇ CSV")
        btn_export.setObjectName("btn-export")
        btn_export.setFont(_font(11))
        btn_export.setFixedHeight(32)
        btn_export.clicked.connect(self._exportar_csv)
        top.addWidget(btn_export)

        btn_sync = QPushButton("↑ Sincronizar")
        btn_sync.setObjectName("btn-sync")
        btn_sync.setFont(_font(11, bold=True))
        btn_sync.setFixedHeight(32)
        btn_sync.clicked.connect(self._forzar_envio)
        top.addWidget(btn_sync)

        layout.addLayout(top)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)

        self.card_now     = NowPlayingCard()
        self.card_hoy     = KPICard("Reproducidas hoy", "0", "+0 vs ayer")
        self.card_pagadas = KPICard("Se pagan", "0", "≥90% escuchadas", OK)
        self.card_cola    = KPICard("En cola", "0", "pendiente envío", WARN)
        self.card_ingresos= KPICard("Ingresos est.", "$0", "COP del día", OK)

        kpi_row.addWidget(self.card_now, 2)
        kpi_row.addWidget(self.card_hoy, 1)
        kpi_row.addWidget(self.card_pagadas, 1)
        kpi_row.addWidget(self.card_cola, 1)
        kpi_row.addWidget(self.card_ingresos, 1)
        layout.addLayout(kpi_row)

        return self._header
        sep.setStyleSheet(f"color: {BORDER};")
        sep.setFixedWidth(1)
        top.addWidget(sep)

        vl = QVBoxLayout()
        vl.setSpacing(2)
        lbl_local_l = QLabel("Establecimiento")
        lbl_local_l.setFont(_font(10))
        lbl_local_l.setStyleSheet(f"color: {FG_DIM};")
        self.lbl_local = QLabel(self.id_local)
        self.lbl_local.setFont(_font(12, bold=True))
        vl.addWidget(lbl_local_l)
        vl.addWidget(self.lbl_local)
        top.addLayout(vl)

        # Badge activo
        badge = QLabel("● activo")
        badge.setFont(_font(10))
        badge.setStyleSheet(f"color: {OK}; background: {OK}22; border-radius: 8px; padding: 2px 8px;")
        top.addWidget(badge)

        top.addStretch()

        btn_export = QPushButton("⬇ Exportar CSV")
        btn_export.setObjectName("btn-export")
        btn_export.clicked.connect(self._exportar_csv)
        top.addWidget(btn_export)

        btn_sync = QPushButton("↑ Sincronizar ahora")
        btn_sync.setObjectName("btn-sync")
        btn_sync.clicked.connect(self._forzar_envio)
        top.addWidget(btn_sync)

        layout.addLayout(top)

        # KPI cards + Now Playing
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)

        self.card_now     = NowPlayingCard()
        self.card_hoy     = KPICard("Reproducidas hoy", "0", "+0 vs ayer")
        self.card_pagadas = KPICard("Se pagan", "0", "≥90% escuchadas", OK)
        self.card_cola    = KPICard("En cola", "0", "pendiente envío", WARN)
        self.card_ingresos= KPICard("Ingresos est.", "$0", "COP del día", OK)

        kpi_row.addWidget(self.card_now, 2)
        kpi_row.addWidget(self.card_hoy, 1)
        kpi_row.addWidget(self.card_pagadas, 1)
        kpi_row.addWidget(self.card_cola, 1)
        kpi_row.addWidget(self.card_ingresos, 1)
        layout.addLayout(kpi_row)

        return self._header

    def _build_toolbar(self):
        self._toolbar = QWidget()
        self._toolbar.setFixedHeight(44)
        self._toolbar.setStyleSheet(f"background: {PANEL}; border-bottom: 1px solid {BORDER};")
        layout = QHBoxLayout(self._toolbar)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(10)

        lbl = QLabel("Historial")
        lbl.setFont(_font(13, bold=True))
        self.lbl_count = QLabel("0")
        self.lbl_count.setFont(_font(11, mono=True))
        self.lbl_count.setStyleSheet(f"color: {FG_DIM};")
        layout.addWidget(lbl)
        layout.addSpacing(6)
        layout.addWidget(self.lbl_count)
        layout.addSpacing(14)

        # Search
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Buscar artista o canción...")
        self.inp_search.setMaximumWidth(300)
        self.inp_search.textChanged.connect(self._on_search)
        layout.addWidget(self.inp_search)

        layout.addStretch()

        # Filtros
        self.filters_group = QWidget()
        fg_layout = QHBoxLayout(self.filters_group)
        fg_layout.setContentsMargins(3, 3, 3, 3)
        fg_layout.setSpacing(2)
        self.filters_group.setStyleSheet(f"background: {PANEL_ALT}; border-radius: 8px;")

        self._filter_btns = {}
        for key, label in [("all","Todo"),("paid","Pagadas"),("unpaid","No pagadas"),("today","Hoy")]:
            btn = QPushButton(label)
            btn.setObjectName("btn-filter")
            btn.setProperty("active", key == "all")
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            fg_layout.addWidget(btn)

        layout.addWidget(self.filters_group)
        return self._toolbar

    def _build_statusbar(self):
        self._statusbar = QWidget()
        self._statusbar.setFixedHeight(26)
        self._statusbar.setStyleSheet(f"background: {PANEL}; border-top: 1px solid {BORDER};")
        layout = QHBoxLayout(self._statusbar)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(18)

        self.dot_status = QLabel("●")
        self.dot_status.setFont(_font(9))
        self.dot_status.setStyleSheet(f"color: {OK};")
        self.lbl_status = QLabel("Conectado")
        self.lbl_status.setFont(_font(11))
        self.lbl_status.setStyleSheet(f"color: {FG_DIM};")
        self.lbl_sync_time = QLabel("")
        self.lbl_sync_time.setFont(_font(11, mono=True))
        self.lbl_sync_time.setStyleSheet(f"color: {FG_FAINT};")
        version = QLabel("CPM Tracks · v3.0")
        version.setFont(_font(11))
        version.setStyleSheet(f"color: {FG_FAINT};")

        layout.addWidget(self.dot_status)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.lbl_sync_time)
        layout.addStretch()
        layout.addWidget(version)
        return self._statusbar

    def _build_table(self):
        columnas = ["FECHA", "HORA", "FUENTE", "ARTISTA", "CANCIÓN", "DUR.", "% REPRODUCIDO", "SE PAGA", "ESTADO"]
        self.table = QTableWidget(0, len(columnas))
        self.table.setHorizontalHeaderLabels(columnas)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i in [0,1,2,5,6,7,8]:
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_click)
        return self.table

    def _on_header_click(self, col):
        """Ordena la tabla al hacer click en el encabezado."""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._actualizar_headers()
        self._aplicar_filtro()

    def _actualizar_headers(self):
        """Actualiza los encabezados con indicador de sort activo."""
        base_cols = ["FECHA", "HORA", "FUENTE", "ARTISTA", "CANCIÓN", "DUR.", "% OÍDO", "SE PAGA", "ESTADO"]
        for i, nombre in enumerate(base_cols):
            if i == self._sort_col:
                flecha = " ▲" if self._sort_asc else " ▼"
                self.table.horizontalHeaderItem(i).setText(nombre + flecha)
            else:
                self.table.horizontalHeaderItem(i).setText(nombre)

    def _toggle_theme(self):
        """Cambia entre modo oscuro y claro en toda la app."""
        self._dark_mode = not self._dark_mode
        if self._dark_mode:
            self.btn_theme.setText("☀ Modo claro")
            self.setStyleSheet(STYLE)
            self._titlebar.setStyleSheet(f"background: {PANEL}; border-bottom: 1px solid {BORDER};")
            self._header.setStyleSheet(f"background: {PANEL}; border-bottom: 1px solid {BORDER};")
            self._toolbar.setStyleSheet(f"background: {PANEL}; border-bottom: 1px solid {BORDER};")
            self._statusbar.setStyleSheet(f"background: {PANEL}; border-top: 1px solid {BORDER};")
            self.filters_group.setStyleSheet(f"background: {PANEL_ALT}; border-radius: 8px;")
            self.table.setStyleSheet(f"background: {BG}; color: {FG}; gridline-color: transparent; border: none; font-size: 12px; selection-background-color: {PANEL};")
            self.centralWidget().setStyleSheet(f"background: {BG};")
        else:
            self.btn_theme.setText("● Modo oscuro")
            self.setStyleSheet(STYLE_LIGHT)
            self._titlebar.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E4E6EB;")
            self._header.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E4E6EB;")
            self._toolbar.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E4E6EB;")
            self._statusbar.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E4E6EB;")
            self.filters_group.setStyleSheet("background: #F2F3F5; border-radius: 8px;")
            self.table.setStyleSheet("background: #FAFAFB; color: #111318; gridline-color: transparent; border: none; font-size: 12px; selection-background-color: #F4F5F7;")
            self.centralWidget().setStyleSheet("background: #FAFAFB;")
        self._aplicar_filtro()

    # ── DATOS ──────────────────────────────────────────────────────────────────

    def _cargar_historial(self):
        rows = database.historial_reciente(200)
        self._all_rows = rows
        self._aplicar_filtro()
        hoy = time.strftime('%Y-%m-%d')
        self._total_hoy = sum(1 for r in rows if r[0].startswith(hoy))
        pagadas_hoy     = sum(1 for r in rows if r[0].startswith(hoy) and (r[7] if len(r)>7 else 0))
        ingresos        = sum((r[6] if len(r)>6 else 0) * 500 / 100 for r in rows
                             if r[0].startswith(hoy) and (r[7] if len(r)>7 else 0))
        self.card_hoy.set_value(self._total_hoy)
        self.card_pagadas.set_value(pagadas_hoy)
        self.card_ingresos.set_value(f"${int(ingresos):,}".replace(",","."))
        self.card_cola.set_value(database.contar_pendientes())

    def _aplicar_filtro(self):
        hoy = time.strftime('%Y-%m-%d')
        rows = list(self._all_rows)
        if self._filter == "paid":
            rows = [r for r in rows if (r[7] if len(r)>7 else 0)]
        elif self._filter == "unpaid":
            rows = [r for r in rows if not (r[7] if len(r)>7 else 0)]
        elif self._filter == "today":
            rows = [r for r in rows if r[0].startswith(hoy)]
        if self._search:
            s = self._search.lower()
            rows = [r for r in rows if s in r[2].lower()]

        # Ordenar por columna si hay una seleccionada
        if self._sort_col is not None:
            col_map = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2, 5: 3, 6: 6, 7: 7, 8: 5}
            db_col = col_map.get(self._sort_col, 0)
            try:
                rows.sort(key=lambda r: r[db_col] if db_col < len(r) else "",
                         reverse=not self._sort_asc)
            except:
                pass

        self._render_tabla(rows)
        self.lbl_count.setText(str(len(rows)))

    def _render_tabla(self, rows):
        # Colores dinamicos segun tema
        fg       = FG      if self._dark_mode else "#111318"
        fg_dim   = FG_DIM  if self._dark_mode else "#5C616B"
        fg_faint = FG_FAINT if self._dark_mode else "#9499A2"

        self.table.setRowCount(0)
        for row in rows:
            timestamp  = row[0]
            fuente     = row[1]
            contenido  = row[2]
            duracion   = row[3]
            enviado    = row[5]
            porcentaje = row[6] if len(row)>6 else 0
            cuenta     = row[7] if len(row)>7 else 0

            fecha = timestamp[:10] if len(timestamp)>10 else timestamp
            hora  = timestamp[11:19] if len(timestamp)>10 else ""

            if " - " in contenido:
                artista, cancion = contenido.split(" - ", 1)
            else:
                artista, cancion = "—", contenido

            pct_col  = OK   if porcentaje >= 90 else WARN if porcentaje >= 50 else BAD
            pago_txt = "✓ Sí" if cuenta else "✗ No"
            pago_col = OK   if cuenta else BAD
            est_txt  = "✓ Enviado" if enviado else "○ Pendiente"
            est_col  = fg_dim if enviado else WARN
            src_col  = SPOTIFY if "Spotify" in fuente else "#ff4444" if "YouTube" in fuente else "#4499ff"

            idx = self.table.rowCount()
            self.table.insertRow(idx)

            def cell(txt, color, bold=False, mono=False):
                item = QTableWidgetItem(str(txt))
                item.setForeground(_col(color))
                if bold or mono:
                    f = item.font()
                    if bold: f.setBold(True)
                    if mono: f.setFamily("Menlo")
                    item.setFont(f)
                return item

            self.table.setItem(idx, 0, cell(fecha,    fg_faint, mono=True))
            self.table.setItem(idx, 1, cell(hora,      fg_faint, mono=True))
            self.table.setItem(idx, 2, cell(fuente,    src_col))
            self.table.setItem(idx, 3, cell(artista,   fg_dim))
            self.table.setItem(idx, 4, cell(cancion,   fg, bold=True))
            self.table.setItem(idx, 5, cell(duracion,  fg_faint, mono=True))
            self.table.setItem(idx, 6, cell(f"{porcentaje:.0f}%", pct_col, bold=True, mono=True))
            self.table.setItem(idx, 7, cell(pago_txt,  pago_col, bold=True))
            self.table.setItem(idx, 8, cell(est_txt,   est_col))
            self.table.setRowHeight(idx, 36)

    # ── ACCIONES ───────────────────────────────────────────────────────────────

    def _set_filter(self, key):
        self._filter = key
        for k, btn in self._filter_btns.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._aplicar_filtro()

    def _on_search(self, text):
        self._search = text
        self._aplicar_filtro()

    def _forzar_envio(self):
        from core.sync import _enviar_batch
        from core import config as cfg
        c          = cfg.cargar()
        endpoint   = c.get("api_endpoint", "")
        token      = c.get("api_token", "")
        pendientes = database.obtener_pendientes(limite=500)
        if not pendientes:
            self.lbl_status.setText("Sin pendientes para enviar")
            return
        self.lbl_status.setText(f"Enviando {len(pendientes)} registros...")
        enviados = _enviar_batch(pendientes, endpoint, token)
        self.lbl_status.setText(f"✓ {len(enviados)} enviados")
        self._cargar_historial()

    def _exportar_csv(self):
        rows = self._all_rows
        if not rows:
            return
        import csv, pathlib
        path = pathlib.Path.home() / "Desktop" / f"cpm_tracks_{time.strftime('%Y%m%d_%H%M')}.csv"
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(["Fecha","Hora","Fuente","Artista","Canción","Duración","% Oído","Se Paga","Estado"])
            for row in rows:
                ts    = row[0]; fecha = ts[:10]; hora = ts[11:19] if len(ts)>10 else ""
                cont  = row[2]
                art, can = cont.split(" - ",1) if " - " in cont else ("—", cont)
                w.writerow([fecha, hora, row[1], art, can, row[3],
                            f"{row[6]:.0f}%" if len(row)>6 else "0%",
                            "Sí" if (row[7] if len(row)>7 else 0) else "No",
                            "Enviado" if row[5] else "Pendiente"])
        self.lbl_status.setText(f"CSV exportado en Escritorio")

    def _refrescar(self):
        # Recargar historial desde DB
        self._cargar_historial()

        n = database.contar_pendientes()
        self.card_cola.set_value(n)
        if n > 0:
            self.dot_status.setStyleSheet(f"color: {WARN};")
            self.lbl_status.setText(f"{n} en cola offline")
        else:
            self.dot_status.setStyleSheet(f"color: {OK};")
            self.lbl_status.setText("Sincronizado")
        self.lbl_sync_time.setText(f"última actualización {time.strftime('%H:%M:%S')}")

        # Actualizar "ahora suena" desde el último registro de la DB
        rows = database.historial_reciente(1)
        if rows:
            row = rows[0]
            contenido = row[2]
            fuente = row[1]
            duracion = row[3]
            if " - " in contenido:
                artista, cancion = contenido.split(" - ", 1)
                titulo = f"{artista} — {cancion}"
            else:
                titulo = contenido
            self.card_now.update(titulo, fuente, duracion)

    def update_now_playing(self, titulo, fuente, duracion=""):
        self.card_now.update(titulo, fuente, duracion)
        self._total_hoy += 1
        self.card_hoy.set_value(self._total_hoy)
        self._cargar_historial()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
