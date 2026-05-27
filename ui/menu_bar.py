"""
CPM Monitor - Icono en la barra de menu de macOS
"""
import rumps
import subprocess
import sys
import os
import time
import fcntl
import logging

log = logging.getLogger("menubar")

from core import database, config, autostart
from core.sync import SyncEngine
from core.scanner import escanear
from core.updater import Updater

LOCK_FILE = os.path.expanduser("~/Library/Application Support/CPMTracks/menubar.lock")


class CPMMenuBar(rumps.App):
    def __init__(self):
        # Lock instancia unica
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        self._lock_fh = open(LOCK_FILE, 'w')
        try:
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            sys.exit(0)

        icon_path = _resource("icon_tray.png")
        super().__init__(
            "CPM",
            icon=icon_path if os.path.exists(icon_path) else None,
            title=None if os.path.exists(icon_path) else "●",
            quit_button=None,
        )

        self.sync_engine  = SyncEngine()
        self._configurado = config.esta_configurado()

        self._play_actual = None
        self._play_inicio = None
        self._play_duracion = 0
        self._play_fuente = ""
        self._play_contenido = ""
        self._play_isrc = ""
        self._play_guardado = False
        # Mínimo de segundos detectando el mismo contenido antes de guardarlo
        # Evita registrar videos de YouTube que el usuario solo roza al scrollear
        self._PLAY_MIN_SEG = 15

        # Mensajes: IDs ya notificados y contador no leídos
        self._mensajes_notificados = set()
        self._msg_tick = 54  # primer check a los ~30s, luego cada 5 min

        self._construir_menu()

        # Timer unico de 5 segundos para scan + UI
        self.timer = rumps.Timer(self._tick, 5)
        self.timer.start()

        self.sync_engine.start()

        # Auto-actualizacion silenciosa (1 vez al dia)
        self.updater = Updater(play_actual_fn=lambda: self._play_actual)
        self.updater.start()

    def _construir_menu(self):
        self.item_estado     = rumps.MenuItem("● Iniciando...")
        self.item_ultimo     = rumps.MenuItem("Sin detecciones aun")
        self.item_porcentaje = rumps.MenuItem("")
        self.item_pendientes = rumps.MenuItem("")
        self.item_mensajes   = rumps.MenuItem("📩 Ver mensajes", callback=self._abrir_mensajes)
        self.item_abrir      = rumps.MenuItem("Abrir panel", callback=self._abrir_panel)
        self.item_sync       = rumps.MenuItem("↑ Sincronizar ahora", callback=self._sincronizar_ahora)
        self.item_autostart  = rumps.MenuItem("", callback=self._toggle_autostart)
        self.menu = [
            self.item_estado,
            self.item_ultimo,
            self.item_porcentaje,
            self.item_pendientes,
            rumps.separator,
            self.item_mensajes,
            self.item_abrir,
            self.item_sync,
            rumps.separator,
            self.item_autostart,
        ]
        self._actualizar_autostart_label()

    def _tick(self, _):
        """Escanea y actualiza UI cada 5 segundos."""
        if not self._configurado and config.esta_configurado():
            self._configurado = True

        # Scanner
        try:
            resultado = escanear()
        except Exception as e:
            log.warning(f"Scanner error: {e}")
            resultado = None

        if resultado:
            # Usar ISRC + contenido como identificador unico de cancion
            id_play = f"{resultado['fuente']}|{resultado['isrc']}|{resultado['contenido']}"

            if self._play_actual != id_play:
                # Nueva cancion — cerrar la anterior
                if self._play_actual is not None and not self._play_guardado:
                    self._guardar_play()
                self._play_actual    = id_play
                self._play_inicio    = time.time()
                self._play_duracion  = resultado.get("duracion_seg", 0)
                self._play_fuente    = resultado["fuente"]
                self._play_contenido = resultado["contenido"]
                self._play_isrc      = resultado["isrc"]
                self._play_guardado  = False

            # Calcular porcentaje por tiempo transcurrido
            # Si la fuente no provee duración (YouTube, etc.) se asume 3:30 = 210s
            _DUR_DEFECTO = 210
            duracion = self._play_duracion if self._play_duracion > 0 else _DUR_DEFECTO
            if self._play_inicio:
                seg = time.time() - self._play_inicio
                pct = min(100, (seg / duracion) * 100)
                emoji = "✓" if pct >= 90 else "◔" if pct >= 50 else "○"
                self.item_porcentaje.title = f"  {emoji} {pct:.0f}%"

            corto = resultado["contenido"][:38] + "…" if len(resultado["contenido"]) > 38 else resultado["contenido"]
            self.item_ultimo.title = f"♪ {resultado['fuente']}: {corto}"

        else:
            if self._play_actual is not None and not self._play_guardado:
                self._guardar_play()
            self._play_actual  = None
            self._play_guardado = False
            self.item_ultimo.title = "Sin detecciones aun"
            self.item_porcentaje.title = ""

        # Estado sync
        try:
            estado, msg = self.sync_engine.estado
            iconos = {"ok": "✓", "sincronizando": "↑", "sin_internet": "○"}
            self.item_estado.title = f"{iconos.get(estado,'?')} {msg.capitalize()}"
        except:
            pass

        n = database.contar_pendientes()
        self.item_pendientes.title = f"{n} en cola" if n > 0 else ""

        # Check de mensajes push cada 60 ticks (5 min)
        self._msg_tick += 1
        if self._msg_tick >= 60 and self._configurado:
            self._msg_tick = 0
            self._verificar_mensajes()

    def _guardar_play(self):
        if not self._play_actual or not self._play_inicio:
            return
        seg_escuchados = time.time() - self._play_inicio
        # No guardar si el play duró menos del mínimo (scroll rápido en YouTube, etc.)
        if seg_escuchados < self._PLAY_MIN_SEG:
            log.debug(f"Play ignorado — duración {seg_escuchados:.0f}s < mínimo {self._PLAY_MIN_SEG}s")
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

    def _sincronizar_ahora(self, _):
        """Fuerza sync inmediato al servidor."""
        self.item_sync.title = "↑ Sincronizando..."
        try:
            self.sync_engine._sincronizar_ahora()
            n = database.contar_pendientes()
            self.item_sync.title = "↑ Sincronizar ahora"
            self.item_pendientes.title = f"{n} en cola" if n > 0 else ""
            if n == 0:
                self.item_estado.title = "✓ Sincronizado"
        except Exception as e:
            self.item_sync.title = "↑ Sincronizar ahora"
            log.warning(f"Sync error: {e}")

    def _verificar_mensajes(self):
        """Chequea mensajes en background. Actualiza contador y lanza banner si hay nuevos."""
        import threading

        def _check():
            try:
                from core.mensajes import MensajesEngine
                mensajes = MensajesEngine().obtener_pendientes()
                n = len(mensajes)

                # Actualizar etiqueta del menú con count
                self.item_mensajes.title = f"📩 Ver mensajes  ({n})" if n > 0 else "📩 Ver mensajes"

                # Solo notificar si hay IDs que no hemos mostrado aún
                nuevos = [m for m in mensajes if m["id"] not in self._mensajes_notificados]
                if nuevos:
                    for m in nuevos:
                        self._mensajes_notificados.add(m["id"])
                    log.info(f"[MENSAJES] {len(nuevos)} nuevos, lanzando banner")
                    subprocess.Popen([sys.executable, "--banner"])
            except Exception as e:
                log.warning(f"Error verificando mensajes: {e}")

        threading.Thread(target=_check, daemon=True).start()

    def _abrir_mensajes(self, _):
        """Abre la ventana de mensajes desde el menú."""
        try:
            subprocess.Popen([sys.executable, "--mensajes"])
        except Exception as e:
            log.warning(f"Error abriendo mensajes: {e}")

    def _abrir_panel(self, _):
        try:
            subprocess.Popen([sys.executable, '--panel'])
        except Exception as e:
            rumps.alert("CPM Monitor", f"No se pudo abrir el panel:\n{e}")

    def _toggle_autostart(self, _):
        if autostart.esta_instalado():
            ok, msg = autostart.desinstalar()
        else:
            ok, msg = autostart.instalar()
        if ok:
            self._actualizar_autostart_label()
        else:
            rumps.alert("CPM Monitor", f"Error: {msg}")

    def _actualizar_autostart_label(self):
        if autostart.esta_instalado():
            self.item_autostart.title = "✓ Iniciar al encender (activo)"
        else:
            self.item_autostart.title = "  Iniciar al encender"


def _resource(name):
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, name)


def run_menu_bar():
    app = CPMMenuBar()
    app.run()
