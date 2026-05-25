"""
CPM Tracks - Ventana de mensajes push
No modal. Cada tarjeta tiene × (cerrar sin leer) y ✓ (marcar leído).
"""
import logging
import threading
import urllib.request
import ssl

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QApplication,
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QPixmap

log = logging.getLogger("mensaje_ui")

BG      = "#0E1116"
PANEL   = "#161A21"
CARD    = "#11151B"
BORDER  = "#212630"
FG      = "#ECEEF2"
DIM     = "#8A8F99"
FAINT   = "#525762"
ACCENT  = "#0A66B7"
ACCENT2 = "#0855A0"
OK      = "#3DDC97"

WIN_STYLE = f"""
QWidget#ventana-mensajes {{
    background: {BG};
    font-family: -apple-system, Arial, sans-serif;
}}
QScrollArea {{ border: none; background: {BG}; }}
QScrollBar:vertical {{
    background: {PANEL}; width: 5px; border-radius: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 2px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

CARD_STYLE = f"""
QFrame#msg-card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
"""


class _ImageLoader:
    def __init__(self, url, callback):
        self._url = url
        self._cb = callback

    def start(self):
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            data = urllib.request.urlopen(self._url, timeout=10, context=ctx).read()
            px = QPixmap()
            px.loadFromData(data)
            if not px.isNull():
                self._cb(px)
        except Exception:
            pass


class MensajeCard(QFrame):
    def __init__(self, msg, engine, on_ocultar, parent=None):
        super().__init__(parent)
        self.setObjectName("msg-card")
        self.setStyleSheet(CARD_STYLE)
        self._msg = msg
        self._engine = engine
        self._on_ocultar = on_ocultar  # callback cuando la tarjeta se cierra
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 14, 14, 14)

        # ── Cabecera: título + botón × (cerrar sin leer) ──────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        titulo = QLabel(self._msg.get("titulo", "Mensaje"))
        titulo.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {FG};")
        titulo.setWordWrap(True)

        btn_x = QPushButton("×")
        btn_x.setFixedSize(22, 22)
        btn_x.setToolTip("Cerrar (no marca como leído)")
        btn_x.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {DIM};
                font-size: 16px; font-weight: 400; border: none; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {FG}; background: #ffffff14; }}
        """)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(self._cerrar)

        header.addWidget(titulo, 1)
        header.addWidget(btn_x, 0, Qt.AlignTop)
        layout.addLayout(header)

        # ── Cuerpo ─────────────────────────────────────────────────────────
        cuerpo_text = self._msg.get("cuerpo", "")
        if cuerpo_text:
            cuerpo = QLabel(cuerpo_text)
            cuerpo.setStyleSheet(f"font-size: 13px; color: {DIM};")
            cuerpo.setWordWrap(True)
            layout.addWidget(cuerpo)

        # ── Imagen ─────────────────────────────────────────────────────────
        img_url = self._msg.get("imagen_url", "")
        if img_url:
            self._img_label = QLabel()
            self._img_label.setFixedHeight(150)
            self._img_label.setAlignment(Qt.AlignCenter)
            self._img_label.setStyleSheet(
                f"border-radius: 8px; background: {BG}; color: {FAINT}; font-size: 11px;"
            )
            self._img_label.setText("Cargando…")
            layout.addWidget(self._img_label)
            loader = _ImageLoader(img_url, self._set_imagen)
            loader.start()
            self._loader = loader

        # ── Botón URL (si lo tiene) ─────────────────────────────────────────
        btn_texto = self._msg.get("boton_texto", "")
        btn_url   = self._msg.get("boton_url", "")
        if btn_texto and btn_url:
            btn = QPushButton(btn_texto)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT}; color: white; border: none;
                    border-radius: 7px; padding: 7px 16px;
                    font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {ACCENT2}; }}
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(btn_url)))
            layout.addWidget(btn, alignment=Qt.AlignLeft)

        # ── Pie de tarjeta: botón "✓ Marcar leído" ─────────────────────────
        footer = QHBoxLayout()
        footer.addStretch()
        btn_leido = QPushButton("✓  Marcar leído")
        btn_leido.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {DIM};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 5px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ color: {OK}; border-color: {OK}; background: {OK}18; }}
        """)
        btn_leido.setCursor(Qt.PointingHandCursor)
        btn_leido.clicked.connect(self._marcar_leido)
        footer.addWidget(btn_leido)
        layout.addLayout(footer)

        outer.addWidget(inner)

    def _set_imagen(self, px):
        px = px.scaled(440, 145, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_label.setPixmap(px)
        self._img_label.setText("")

    def _cerrar(self):
        """Oculta la tarjeta sin marcar como leído."""
        self.hide()
        self._on_ocultar()

    def _marcar_leido(self):
        """Marca como leído en el servidor y oculta la tarjeta."""
        threading.Thread(
            target=self._engine.marcar_leido,
            args=(self._msg["id"],),
            daemon=True,
        ).start()
        self.hide()
        self._on_ocultar()


class VentanaMensaje(QWidget):
    def __init__(self, mensajes, engine, parent=None):
        super().__init__(parent)
        self.setObjectName("ventana-mensajes")
        self._mensajes = mensajes
        self._engine = engine
        self._cards = []
        self.setWindowTitle(f"CPM Monitor · Mensajes ({len(mensajes)})")
        self.setFixedWidth(500)
        self.setMinimumHeight(200)
        self.setMaximumHeight(700)
        self.setStyleSheet(WIN_STYLE)
        # Ventana normal, no modal
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            f"background: {PANEL}; border-bottom: 1px solid {BORDER};"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 14, 20, 14)

        n = len(self._mensajes)
        lbl_title = QLabel("Mensajes")
        lbl_title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {FG};"
        )
        lbl_count = QLabel(f"  {n}  ")
        lbl_count.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {ACCENT};"
            f"background: {ACCENT}22; border-radius: 10px; padding: 2px 0;"
        )

        btn_todos = QPushButton("Marcar todos leídos")
        btn_todos.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {DIM};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 5px 12px; font-size: 11px;
            }}
            QPushButton:hover {{ color: {OK}; border-color: {OK}; background: {OK}18; }}
        """)
        btn_todos.setCursor(Qt.PointingHandCursor)
        btn_todos.clicked.connect(self._marcar_todos)

        hl.addWidget(lbl_title)
        hl.addWidget(lbl_count)
        hl.addStretch()
        hl.addWidget(btn_todos)
        root.addWidget(header)

        # ── Scroll con tarjetas ───────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        container.setStyleSheet(f"background: {BG};")
        self._cards_layout = QVBoxLayout(container)
        self._cards_layout.setSpacing(10)
        self._cards_layout.setContentsMargins(14, 14, 14, 14)

        for msg in self._mensajes:
            card = MensajeCard(msg, self._engine, self._on_card_oculta)
            self._cards.append(card)
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

    def _on_card_oculta(self):
        """Llamado cuando una tarjeta se cierra. Si no quedan, cierra la ventana."""
        visibles = [c for c in self._cards if not c.isHidden()]
        if not visibles:
            self.close()

    def _marcar_todos(self):
        for card in self._cards:
            if not card.isHidden():
                card._marcar_leido()
