"""
CPM Monitor - Icono en la bandeja del sistema para Windows
Equivalente a ui/menu_bar.py pero usando QSystemTrayIcon en lugar de rumps.
"""
import sys
import os
import time
import threading
import logging
import subprocess

log = logging.getLogger("tray_win")

from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu,
                              QAction, QMessageBox)
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt5.QtCore import QTimer, Qt

from core import database, config, autostart
from core.sync import SyncEngine
from core.scanner_win import escanear
from core.updater import Updater


def _resource(name):
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    return os.path.join(base, name)


def _make_fallback_icon():
    """Genera un icono simple si no existe el PNG."""
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#1A7FD4"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, 32, 32, 6, 6)
    p.end()
    return QIcon(px)


class CPMTray:
    def __init__(self, app: QApplication):
        self._app = app
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("CPM Monitor")

        icon_path = _resource("icon_tray.png")
        if os.path.exists(icon_path):
            self._tray.setIcon(QIcon(icon_path))
        else:
            self._tray.setIcon(_make_fallback_icon())

        self.sync_engine = SyncEngine()
        self._configurado = config.esta_configurado()

        self._play_actual = None
        self._play_inicio = None
        self._play_duracion = 0
        self._play_fuente = ""
        self._play_contenido = ""
        self._play_isrc = ""
        self._play_guardado = False

        self._mensajes_notificados = set()
        self._msg_tick = 54

        self._construir_menu()
        self._tray.show()

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(5000)

        self.sync_engine.start()

        self.updater = Updater(play_actual_fn=lambda: self._play_actual)
        self.updater.start()

    def _construir_menu(self):
        self._menu = QMenu()  # referencia fuerte para evitar garbage collection
        menu = self._menu

        self._act_estado = QAction("● Iniciando...")
        self._act_estado.setEnabled(False)

        self._act_ultimo = QAction("Sin detecciones aun")
        self._act_ultimo.setEnabled(False)

        self._act_porcentaje = QAction("")
        self._act_porcentaje.setEnabled(False)
        self._act_porcentaje.setVisible(False)

        self._act_pendientes = QAction("")
        self._act_pendientes.setEnabled(False)
        self._act_pendientes.setVisible(False)

        self._act_mensajes = QAction("📩 Ver mensajes")
        self._act_mensajes.triggered.connect(self._abrir_mensajes)

        self._act_panel = QAction("Abrir panel")
        self._act_panel.triggered.connect(self._abrir_panel)

        self._act_sync = QAction("↑ Sincronizar ahora")
        self._act_sync.triggered.connect(self._sincronizar_ahora)

        self._act_autostart = QAction("")
        self._act_autostart.triggered.connect(self._toggle_autostart)
        self._actualizar_autostart_label()

        act_salir = QAction("Salir")
        act_salir.triggered.connect(self._salir)

        menu.addAction(self._act_estado)
        menu.addAction(self._act_ultimo)
        menu.addAction(self._act_porcentaje)
        menu.addAction(self._act_pendientes)
        menu.addSeparator()
        menu.addAction(self._act_mensajes)
        menu.addAction(self._act_panel)
        menu.addAction(self._act_sync)
        menu.addSeparator()
        menu.addAction(self._act_autostart)
        menu.addSeparator()
        menu.addAction(act_salir)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activate)

    def _on_activate(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._abrir_panel()

    def _tick(self):
        """Escanea y actualiza UI cada 5 segundos."""
        if not self._configurado and config.esta_configurado():
            self._configurado = True

        try:
            resultado = escanear()
        except Exception as e:
            log.warning(f"Scanner error: {e}")
            resultado = None

        if resultado:
            id_play = f"{resultado['fuente']}|{resultado['isrc']}|{resultado['contenido']}"

            if self._play_actual != id_play:
                if self._play_actual is not None and not self._play_guardado:
                    self._guardar_play()
                self._play_actual    = id_play
                self._play_inicio    = time.time()
                self._play_duracion  = resultado.get("duracion_seg", 0)
                self._play_fuente    = resultado["fuente"]
                self._play_contenido = resultado["contenido"]
                self._play_isrc      = resultado["isrc"]
                self._play_guardado  = False

            duracion = self._play_duracion
            if self._play_inicio:
                seg = time.time() - self._play_inicio
                if duracion > 0:
                    pct = min(100, (seg / duracion) * 100)
                    emoji = "✓" if pct >= 90 else "◔" if pct >= 50 else "○"
                    self._act_porcentaje.setText(f"  {emoji} {pct:.0f}%")
                    self._act_porcentaje.setVisible(True)
                else:
                    self._act_porcentaje.setText(f"  ⏱ {int(seg)}s")
                    self._act_porcentaje.setVisible(True)

            corto = resultado["contenido"][:38] + "…" if len(resultado["contenido"]) > 38 else resultado["contenido"]
            self._act_ultimo.setText(f"♪ {resultado['fuente']}: {corto}")
            self._tray.setToolTip(f"CPM Monitor — {corto}")

        else:
            if self._play_actual is not None and not self._play_guardado:
                self._guardar_play()
            self._play_actual   = None
            self._play_guardado = False
            self._act_ultimo.setText("Sin detecciones aun")
            self._act_porcentaje.setVisible(False)
            self._tray.setToolTip("CPM Monitor")

        # Estado sync
        try:
            estado, msg = self.sync_engine.estado
            iconos = {"ok": "✓", "sincronizando": "↑", "sin_internet": "○"}
            self._act_estado.setText(f"{iconos.get(estado,'?')} {msg.capitalize()}")
        except Exception:
            pass

        n = database.contar_pendientes()
        if n > 0:
            self._act_pendientes.setText(f"{n} en cola")
            self._act_pendientes.setVisible(True)
        else:
            self._act_pendientes.setVisible(False)

        self._msg_tick += 1
        if self._msg_tick >= 60 and self._configurado:
            self._msg_tick = 0
            self._verificar_mensajes()

    def _guardar_play(self):
        if not self._play_actual or not self._play_inicio:
            return
        cfg = config.cargar()
        id_local = cfg.get("id_local", "SIN_CONFIGURAR")
        seg_escuchados = time.time() - self._play_inicio
        duracion = self._play_duracion
        seg_escuchados = max(0, min(seg_escuchados, duracion if duracion > 0 else seg_escuchados))
        mins = int(duracion // 60)
        secs = int(duracion % 60)
        dur_str = f"{mins:02d}:{secs:02d}" if duracion > 0 else "--:--"
        database.guardar_play(
            id_local=id_local,
            fuente=self._play_fuente,
            contenido=self._play_contenido,
            duracion=dur_str,
            isrc=self._play_isrc,
            porcentaje=round(min(100, (seg_escuchados / duracion * 100)) if duracion > 0 else 0, 1),
            segundos_escuchados=round(seg_escuchados, 1),
            duracion_seg=duracion,
        )
        self._play_guardado = True

    def _sincronizar_ahora(self):
        self._act_sync.setText("↑ Sincronizando...")
        try:
            self.sync_engine._sincronizar_ahora()
            n = database.contar_pendientes()
            self._act_sync.setText("↑ Sincronizar ahora")
            if n > 0:
                self._act_pendientes.setText(f"{n} en cola")
                self._act_pendientes.setVisible(True)
            else:
                self._act_pendientes.setVisible(False)
                self._act_estado.setText("✓ Sincronizado")
        except Exception as e:
            self._act_sync.setText("↑ Sincronizar ahora")
            log.warning(f"Sync error: {e}")

    @staticmethod
    def _exe_dir():
        """Directorio del ejecutable — necesario para que Windows encuentre las DLLs de PyInstaller."""
        return os.path.dirname(os.path.abspath(sys.executable))

    def _verificar_mensajes(self):
        def _check():
            try:
                from core.mensajes import MensajesEngine
                mensajes = MensajesEngine().obtener_pendientes()
                n = len(mensajes)
                self._act_mensajes.setText(f"📩 Ver mensajes  ({n})" if n > 0 else "📩 Ver mensajes")
                nuevos = [m for m in mensajes if m["id"] not in self._mensajes_notificados]
                if nuevos:
                    for m in nuevos:
                        self._mensajes_notificados.add(m["id"])
                    log.info(f"[MENSAJES] {len(nuevos)} nuevos, lanzando banner")
                    subprocess.Popen([sys.executable, "--banner"],
                                     cwd=self._exe_dir())
            except Exception as e:
                log.warning(f"Error verificando mensajes: {e}")
        threading.Thread(target=_check, daemon=True).start()

    def _abrir_mensajes(self):
        try:
            subprocess.Popen([sys.executable, "--mensajes"],
                             cwd=self._exe_dir())
        except Exception as e:
            log.warning(f"Error abriendo mensajes: {e}")

    def _abrir_panel(self):
        try:
            subprocess.Popen([sys.executable, "--panel"],
                             cwd=self._exe_dir())
        except Exception as e:
            log.warning(f"Error abriendo panel: {e}")

    def _toggle_autostart(self):
        if autostart.esta_instalado():
            ok, msg = autostart.desinstalar()
        else:
            ok, msg = autostart.instalar()
        if ok:
            self._actualizar_autostart_label()
        else:
            self._tray.showMessage("CPM Monitor", f"Error: {msg}", QSystemTrayIcon.Warning, 3000)

    def _actualizar_autostart_label(self):
        if autostart.esta_instalado():
            self._act_autostart.setText("✓ Iniciar al encender (activo)")
        else:
            self._act_autostart.setText("  Iniciar al encender")

    def _salir(self):
        self._timer.stop()
        self.sync_engine.stop()
        self.updater.stop()
        self._tray.hide()
        self._app.quit()


def run_tray():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray = CPMTray(app)
    sys.exit(app.exec_() if hasattr(app, 'exec_') else app.exec())
