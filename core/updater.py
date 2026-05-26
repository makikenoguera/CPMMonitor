"""
CPM Monitor - Auto-actualizacion silenciosa
Verifica una vez al dia si hay nueva version disponible.
Descarga e instala en background sin interrumpir la reproduccion.
Compatible: macOS (.pkg) y Windows (.exe).
"""
import os
import sys
import time
import threading
import logging
import subprocess
import urllib.request
import json
import tempfile
import platform

log = logging.getLogger("updater")

_IS_WIN = platform.system() == "Windows"

VERSION_ACTUAL  = "4.3"
VERSION_URL     = "https://monitor.cpmtracks.com/monitor-install/version.json"
CHECK_INTERVALO = 86400  # 24 horas en segundos
ULTIMA_REVISION = 0


def _ssl_context():
    import ssl
    ctx = ssl.create_default_context()
    try:
        import certifi, os
        ca = certifi.where()
        # En PyInstaller onefile, certifi puede estar en _MEIPASS
        if not os.path.exists(ca):
            import sys
            if hasattr(sys, '_MEIPASS'):
                ca = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
        if os.path.exists(ca):
            ctx = ssl.create_default_context(cafile=ca)
    except (ImportError, Exception):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _verificar_internet():
    try:
        urllib.request.urlopen("https://8.8.8.8", timeout=5, context=_ssl_context())
        return True
    except:
        try:
            import socket
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except:
            return False


def _obtener_version_remota():
    try:
        req = urllib.request.urlopen(VERSION_URL, timeout=10, context=_ssl_context())
        data = json.loads(req.read().decode('utf-8'))
        return data
    except Exception as e:
        log.warning(f"[UPDATER] Error obteniendo version: {e}")
        return None


def _version_mayor(remota, local):
    """Compara versiones semanticas."""
    try:
        r = tuple(int(x) for x in str(remota).split('.'))
        l = tuple(int(x) for x in str(local).split('.'))
        return r > l
    except:
        return False


def _descargar_e_instalar(url, version, play_actual_fn):
    """Descarga el instalador y lo ejecuta cuando no hay reproduccion activa."""
    try:
        log.info(f"[UPDATER] Descargando version {version}...")
        suffix = '.exe' if _IS_WIN else '.pkg'
        tmp = tempfile.mktemp(suffix=suffix, prefix='CPMMonitor_update_')
        urllib.request.urlretrieve(url, tmp)
        log.info(f"[UPDATER] Descarga completada: {tmp}")

        # Esperar a que no haya reproduccion activa (max 10 minutos)
        intentos = 0
        while play_actual_fn() is not None and intentos < 120:
            time.sleep(5)
            intentos += 1

        log.info(f"[UPDATER] Instalando version {version}...")

        if _IS_WIN:
            # En Windows: ejecutar el .exe con /SILENT y reiniciar
            resultado = subprocess.run(
                [tmp, '/SILENT', '/NORESTART'],
                capture_output=True, text=True, timeout=300
            )
            if resultado.returncode == 0:
                log.info(f"[UPDATER] Version {version} instalada correctamente")
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                # Reiniciar app Windows
                time.sleep(3)
                exe_path = os.path.join(
                    os.environ.get('LOCALAPPDATA', ''), 'CPMTracks', 'CPMMonitor.exe'
                )
                if os.path.exists(exe_path):
                    subprocess.Popen([exe_path])
                else:
                    # Fallback: re-lanzar el ejecutable actual
                    subprocess.Popen([sys.executable] + sys.argv)
            else:
                log.warning(f"[UPDATER] Error instalando (Windows): {resultado.stderr}")
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        else:
            # macOS: instalar .pkg con sudo installer
            resultado = subprocess.run(
                ['sudo', 'installer', '-pkg', tmp, '-target', '/'],
                capture_output=True, text=True, timeout=300
            )
            if resultado.returncode == 0:
                log.info(f"[UPDATER] Version {version} instalada correctamente")
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                # Reiniciar la app despues de instalar
                time.sleep(3)
                subprocess.Popen(['open', '/Applications/CPMMonitor.app'])
            else:
                log.warning(f"[UPDATER] Error instalando (macOS): {resultado.stderr}")
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    except Exception as e:
        log.warning(f"[UPDATER] Error en actualizacion: {e}")


class Updater:
    def __init__(self, play_actual_fn=None):
        """
        play_actual_fn: funcion que retorna None si no hay reproduccion activa.
        """
        self._play_actual_fn = play_actual_fn or (lambda: None)
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("[UPDATER] Iniciado")

    def stop(self):
        self._running = False

    def _loop(self):
        global ULTIMA_REVISION
        # Esperar 60 segundos al arranque antes de verificar
        time.sleep(60)
        while self._running:
            try:
                if _verificar_internet():
                    self._verificar()
                    ULTIMA_REVISION = time.time()
            except Exception as e:
                log.warning(f"[UPDATER] Error en loop: {e}")
            # Esperar 24 horas para la siguiente verificacion
            time.sleep(CHECK_INTERVALO)

    def _verificar(self):
        data = _obtener_version_remota()
        if not data:
            return
        version_remota = data.get("version", "0")
        # Seleccionar URL según plataforma
        if _IS_WIN:
            url = data.get("url_win_exe", data.get("url", ""))
        else:
            url = data.get("url", "")

        if not url:
            log.warning("[UPDATER] No hay URL de descarga disponible para esta plataforma")
            return

        if _version_mayor(version_remota, VERSION_ACTUAL):
            log.info(f"[UPDATER] Nueva version disponible: {version_remota}")
            t = threading.Thread(
                target=_descargar_e_instalar,
                args=(url, version_remota, self._play_actual_fn),
                daemon=True
            )
            t.start()
        else:
            log.info(f"[UPDATER] Version actualizada: {VERSION_ACTUAL}")
