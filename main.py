"""
CPM Tracks — Punto de entrada principal
Modo --background : solo menu bar / bandeja + scanner (sin ventana visible)
Modo --panel      : abre solo la ventana PyQt5
Modo default      : primer arranque con setup si no está configurado
"""
import sys
import os
import platform
import logging

_IS_WIN = platform.system() == "Windows"

# Logging
if _IS_WIN:
    _log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CPMTracks", "Logs")
else:
    _log_dir = os.path.expanduser("~/Library/Logs/CPMTracks")
os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(os.path.join(_log_dir, "agent_error.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ]
)

from core import database, config, autostart
from core.sync import SyncEngine

database.init_db()


def _ocultar_dock():
    """Evita que el proceso aparezca como sesión en el Dock (solo macOS)."""
    if _IS_WIN:
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass


def _modo_background():
    """
    Modo silencioso: menu bar (macOS) o bandeja del sistema (Windows) + scanner.
    La ventana del panel NO se inicia aquí.
    """
    if _IS_WIN:
        from ui.tray_win import run_tray
        run_tray()
    else:
        from ui.menu_bar import run_menu_bar
        run_menu_bar()


def _modo_panel():
    """Abre solo la ventana del panel (subproceso desde el menú/bandeja)."""
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        from PyQt6.QtWidgets import QApplication
    from ui.window import VentanaPrincipal

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    _ocultar_dock()

    ventana = VentanaPrincipal()
    ventana.show()
    ventana.raise_()
    ventana.activateWindow()

    sys.exit(app.exec_() if hasattr(app, 'exec_') else app.exec())


def _primer_arranque():
    """
    Flujo completo de primer arranque:
    1. Mostrar setup si no está configurado.
    2. Instalar autostart.
    3. Lanzar modo background.
    """
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        from PyQt6.QtWidgets import QApplication
    from ui.setup import VentanaSetup

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not config.esta_configurado():
        setup = VentanaSetup()
        resultado = setup.exec_() if hasattr(setup, "exec_") else setup.exec()
        if resultado != 1:
            sys.exit(0)

    if not autostart.esta_instalado():
        ok, msg = autostart.instalar()
        logging.info(f"Autostart: {msg}")

    app.quit()

    import subprocess
    exe = sys.executable
    try:
        script = os.path.abspath(__file__)
        if os.path.exists(script):
            subprocess.Popen([exe, script, '--background'])
        else:
            subprocess.Popen([exe, '--background'])
    except Exception:
        subprocess.Popen([exe, '--background'])
    sys.exit(0)


def _modo_mensajes():
    """Muestra ventana de mensajes pendientes."""
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        from PyQt6.QtWidgets import QApplication
    from ui.mensaje_ui import VentanaMensaje
    from core.mensajes import MensajesEngine

    engine = MensajesEngine()
    mensajes = engine.obtener_pendientes()

    if mensajes:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        _ocultar_dock()
        ventana = VentanaMensaje(mensajes, engine)
        ventana.show()
        ventana.raise_()
        ventana.activateWindow()
        sys.exit(app.exec_() if hasattr(app, 'exec_') else app.exec())


def _modo_banner():
    """Banner flotante pequeño cuando hay mensajes nuevos."""
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        from PyQt6.QtWidgets import QApplication
    from core.mensajes import MensajesEngine

    mensajes = MensajesEngine().obtener_pendientes()
    logging.info(f"[BANNER] mensajes pendientes: {len(mensajes)}")
    if not mensajes:
        return

    if not _IS_WIN:
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except Exception:
            pass

    from ui.banner_ui import BannerMensajes
    app = QApplication(sys.argv)
    _ocultar_dock()
    banner = BannerMensajes(len(mensajes), mensajes[0])
    banner.show()
    banner.raise_()
    logging.info("[BANNER] ventana mostrada")
    sys.exit(app.exec_() if hasattr(app, 'exec_') else app.exec())


if __name__ == "__main__":
    args = sys.argv[1:]

    if '--background' in args:
        _modo_background()
    elif '--panel' in args:
        _modo_panel()
    elif '--mensajes' in args:
        _modo_mensajes()
    elif '--banner' in args:
        _modo_banner()
    else:
        _primer_arranque()
