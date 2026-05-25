"""
CPM Tracks - Banner flotante de notificación de mensajes nuevos.
Aparece debajo del menu bar, esquina superior derecha. No es modal.
"""
import subprocess
import sys
import logging

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QApplication, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPainter, QColor, QPainterPath, QBrush

log = logging.getLogger("banner_ui")

# ── Colores ───────────────────────────────────────────────────────────────────
BG      = "#0F1318"
BORDER  = "#1E2A3A"
FG      = "#ECEEF2"
DIM     = "#7A8499"
ACCENT  = "#1A7FD4"
ACCENT_D = "#0A5A9C"
OK_BG   = "#1A7FD418"

W, H = 340, 82


class LogoCPM(QWidget):
    """Ícono cuadrado redondeado con texto CPM — replica el brand del dashboard."""
    def __init__(self, size=34, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._size, self._size, 7, 7)
        p.fillPath(path, QColor(ACCENT))
        p.setPen(QColor("#FFFFFF"))
        font = QFont("-apple-system", 9, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        p.setFont(font)
        p.drawText(0, 0, self._size, self._size, Qt.AlignCenter, "CPM")


class BannerMensajes(QWidget):
    def __init__(self, count, mensaje_reciente):
        super().__init__()
        self._count = count
        self._reciente = mensaje_reciente
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.setFixedSize(W, H)
        self._build()
        self._position()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start(9000)

    def paintEvent(self, _):
        """Fondo oscuro con borde redondeado y línea de acento superior."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Fondo
        path = QPainterPath()
        path.addRoundedRect(0, 0, W, H, 10, 10)
        p.fillPath(path, QColor(BG))
        # Borde
        p.setPen(QColor(BORDER))
        p.drawPath(path)
        # Línea de acento en el top
        accent_path = QPainterPath()
        accent_path.addRoundedRect(0, 0, W, 3, 1, 1)
        p.fillPath(accent_path, QColor(ACCENT))

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 12, 12)
        root.setSpacing(6)

        # ── Fila superior: logo + titulo + botón cerrar ───────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        logo = LogoCPM(28)
        top.addWidget(logo)

        info = QVBoxLayout()
        info.setSpacing(2)

        n = self._count
        lbl_app = QLabel("CPM Monitor")
        lbl_app.setStyleSheet(f"font-size: 10px; color: {DIM}; font-weight: 500;")

        lbl_count = QLabel(f"{n} mensaje{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''}")
        lbl_count.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {FG};")

        info.addWidget(lbl_app)
        info.addWidget(lbl_count)
        top.addLayout(info, 1)

        btn_x = QPushButton("×")
        btn_x.setFixedSize(20, 20)
        btn_x.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {DIM};
                font-size: 16px; font-weight: 300; border: none;
            }}
            QPushButton:hover {{ color: {FG}; }}
        """)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(self._dismiss)
        top.addWidget(btn_x, 0, Qt.AlignTop)

        root.addLayout(top)

        # ── Fila inferior: título del mensaje + botón ver ─────────────────
        bot = QHBoxLayout()
        bot.setSpacing(10)

        titulo_raw = self._reciente.get("titulo", "")
        if titulo_raw:
            # Truncar si es muy largo
            titulo_txt = titulo_raw if len(titulo_raw) <= 32 else titulo_raw[:30] + "…"
            lbl_titulo = QLabel('“' + titulo_txt + '”')
            lbl_titulo.setStyleSheet(
                f"font-size: 11px; color: {DIM}; font-style: italic;"
            )
            bot.addWidget(lbl_titulo, 1)

        btn_ver = QPushButton("Ver mensajes →")
        btn_ver.setFixedHeight(26)
        btn_ver.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 6px;
                padding: 0 14px; font-size: 11px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT_D}; }}
        """)
        btn_ver.setCursor(Qt.PointingHandCursor)
        btn_ver.clicked.connect(self._abrir_mensajes)
        bot.addWidget(btn_ver)

        root.addLayout(bot)

    def _position(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - W - 16
        y = 32
        self.move(x, y)

    def _abrir_mensajes(self):
        try:
            subprocess.Popen([sys.executable, "--mensajes"])
        except Exception as e:
            log.warning(f"Error abriendo mensajes: {e}")
        self._dismiss()

    def _dismiss(self):
        self._timer.stop()
        self.close()
