"""
CPM Tracks - Pantalla de activación (primer arranque)
El usuario ingresa email y clave del servidor.
La app se configura automáticamente.
"""
import sys
import os
import urllib.request
import urllib.error
import json
import ssl

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui  import QPixmap, QIcon, QFont, QCursor, QDesktopServices

from core import config

API = "https://monitor.cpmtracks.com"

BG_BASE    = "#0D0D0D"
BG_SURFACE = "#181818"
GREEN      = "#1DB954"
TEXT_PRI   = "#FFFFFF"
TEXT_SEC   = "#B3B3B3"
TEXT_HINT  = "#535353"
BORDER     = "#2a2a2a"
RED        = "#e74c3c"

STYLE = f"""
    QDialog  {{ background-color: {BG_BASE}; }}
    QWidget  {{ background-color: {BG_BASE}; }}
    QLabel   {{ color: {TEXT_PRI}; }}
    QFrame   {{ background-color: {BG_BASE}; }}
    QLineEdit {{
        background-color: {BG_SURFACE};
        color: {TEXT_PRI};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 12px 14px;
        font-size: 14px;
    }}
    QLineEdit:focus {{ border: 1px solid {GREEN}; }}
    QPushButton#btn-primary {{
        background-color: {GREEN};
        color: #000000;
        border: none;
        border-radius: 24px;
        padding: 14px 32px;
        font-size: 15px;
    }}
    QPushButton#btn-primary:hover {{ background-color: #1ed760; }}
    QPushButton#btn-primary:disabled {{ background-color: #1a4a2a; color: #444; }}
    QPushButton#btn-toggle {{
        background-color: transparent;
        color: {TEXT_HINT};
        border: none;
        font-size: 16px;
        padding: 0px;
    }}
    QPushButton#btn-toggle:hover {{ color: {TEXT_SEC}; }}
"""

def _resource(name):
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(base, name)

def _font(size, bold=False):
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f

class LoginWorker(QThread):
    success = pyqtSignal(dict)
    error   = pyqtSignal(str)

    def __init__(self, email, password):
        super().__init__()
        self.email    = email
        self.password = password

    def run(self):
        try:
            body = json.dumps({"email": self.email, "password": self.password}).encode()
            req  = urllib.request.Request(
                f"{API}/auth/instalar", data=body,
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=10, context=_SSL)
            self.success.emit(json.loads(resp.read().decode()))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("error", "Credenciales incorrectas")
            except:
                msg = "Credenciales incorrectas"
            self.error.emit(msg)
        except Exception:
            self.error.emit("Sin conexión. Verifica tu internet e intenta de nuevo.")

class VentanaSetup(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CPM Tracks — Activación")
        self.setFixedSize(460, 570)
        self.setStyleSheet(STYLE)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        icon_path = _resource("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(44, 36, 44, 36)
        layout.setSpacing(0)

        # Logo
        logo_path = _resource("logo.png")
        if os.path.exists(logo_path):
            lbl_logo = QLabel()
            lbl_logo.setPixmap(QPixmap(logo_path).scaledToWidth(160, Qt.SmoothTransformation))
            lbl_logo.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl_logo)
            layout.addSpacing(20)

        # Título
        lbl_titulo = QLabel("Activa tu monitor")
        lbl_titulo.setFont(_font(20, bold=True))
        lbl_titulo.setAlignment(Qt.AlignCenter)
        lbl_titulo.setStyleSheet(f"color: {TEXT_PRI};")
        layout.addWidget(lbl_titulo)
        layout.addSpacing(6)

        lbl_sub = QLabel("Ingresa con las credenciales que recibiste por correo electrónico")
        lbl_sub.setFont(_font(13))
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet(f"color: {TEXT_SEC};")
        layout.addWidget(lbl_sub)
        layout.addSpacing(28)

        # Email
        layout.addWidget(self._label("Email"))
        layout.addSpacing(6)
        self.inp_email = QLineEdit()
        self.inp_email.setPlaceholderText("tu@email.com")
        self.inp_email.setFixedHeight(48)
        self.inp_email.returnPressed.connect(self._activar)
        layout.addWidget(self.inp_email)
        layout.addSpacing(16)

        # Contraseña
        layout.addWidget(self._label("Contraseña"))
        layout.addSpacing(6)
        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(0)
        self.inp_pwd = QLineEdit()
        self.inp_pwd.setPlaceholderText("Tu contraseña temporal")
        self.inp_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pwd.setFixedHeight(48)
        self.inp_pwd.returnPressed.connect(self._activar)
        self.btn_toggle = QPushButton("👁")
        self.btn_toggle.setObjectName("btn-toggle")
        self.btn_toggle.setFixedSize(44, 48)
        self.btn_toggle.clicked.connect(self._toggle_pwd)
        pwd_row.addWidget(self.inp_pwd)
        pwd_row.addWidget(self.btn_toggle)
        layout.addLayout(pwd_row)
        layout.addSpacing(10)

        # Estado
        self.lbl_estado = QLabel("")
        self.lbl_estado.setFont(_font(12))
        self.lbl_estado.setAlignment(Qt.AlignCenter)
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet(f"color: {RED};")
        self.lbl_estado.setFixedHeight(36)
        layout.addWidget(self.lbl_estado)
        layout.addSpacing(6)

        # Botón
        self.btn_activar = QPushButton("Activar monitor")
        self.btn_activar.setObjectName("btn-primary")
        self.btn_activar.setFont(_font(15, bold=True))
        self.btn_activar.setFixedHeight(52)
        self.btn_activar.clicked.connect(self._activar)
        layout.addWidget(self.btn_activar)

        layout.addStretch()

        # Banner registro
        banner = QFrame()
        banner.setStyleSheet(f"QFrame {{ background-color: #111; border: 1px solid {BORDER}; border-radius: 10px; }}")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(16, 14, 16, 14)
        bl.setSpacing(8)

        lbl_b = QLabel("¿Tu establecimiento aún no genera ingresos con la música?")
        lbl_b.setFont(_font(12))
        lbl_b.setWordWrap(True)
        lbl_b.setAlignment(Qt.AlignCenter)
        lbl_b.setStyleSheet(f"color: {TEXT_SEC}; background: transparent; border: none;")
        bl.addWidget(lbl_b)

        btn_reg = QPushButton("Registra tu local y comienza a cobrar →")
        btn_reg.setFont(_font(12, bold=True))
        btn_reg.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_reg.clicked.connect(self._abrir_registro)
        btn_reg.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {GREEN}; border: none; font-size: 12px; }}
            QPushButton:hover {{ color: #1ed760; }}
        """)
        bl.addWidget(btn_reg)
        layout.addWidget(banner)

    def _label(self, texto):
        lbl = QLabel(texto)
        lbl.setFont(_font(12, bold=True))
        lbl.setStyleSheet(f"color: {TEXT_SEC};")
        return lbl

    def _toggle_pwd(self):
        if self.inp_pwd.echoMode() == QLineEdit.EchoMode.Password:
            self.inp_pwd.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle.setText("🙈")
        else:
            self.inp_pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle.setText("👁")

    def _abrir_registro(self):
        QDesktopServices.openUrl(QUrl("https://monitor.cpmtracks.com/registro"))

    def _activar(self):
        email = self.inp_email.text().strip().lower()
        pwd   = self.inp_pwd.text()
        if not email:
            self._set_error("Ingresa tu correo electrónico"); return
        if not pwd:
            self._set_error("Ingresa tu contraseña"); return
        self.btn_activar.setEnabled(False)
        self.btn_activar.setText("Conectando...")
        self.lbl_estado.setStyleSheet(f"color: {GREEN};")
        self.lbl_estado.setText("Verificando credenciales...")
        self._worker = LoginWorker(email, pwd)
        self._worker.success.connect(self._on_success)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_success(self, data):
        self.lbl_estado.setText("✓ Todo listo. Iniciando monitor...")
        cfg = config.cargar()
        cfg.update({
            "id_local":     data.get("id_local", ""),
            "nombre_local": data.get("nombre_local", ""),
            "tipo_local":   data.get("tipo_local", ""),
            "api_endpoint": data.get("api_endpoint", "https://monitor.cpmtracks.com/v1/plays"),
            "api_token":    data.get("api_token", ""),
            "configurado":  True,
        })
        config.guardar(cfg)
        import time; time.sleep(1)
        self.accept()

    def _on_error(self, msg):
        self._set_error(msg)
        self.btn_activar.setEnabled(True)
        self.btn_activar.setText("Activar monitor")

    def _set_error(self, msg):
        self.lbl_estado.setStyleSheet(f"color: {RED};")
        self.lbl_estado.setText(msg)
