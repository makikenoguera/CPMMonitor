"""
CPM Tracks - Motor de sincronización offline-first
Envía la cola pendiente al servidor cuando hay conexión.
Corre en un hilo separado para no bloquear la UI.
"""
import threading
import time
import logging
import urllib.request
import urllib.error
import json
import ssl

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

from core import database, config

log = logging.getLogger("sync")


def _hay_internet(host="8.8.8.8", timeout=3):
    """Chequeo rápido de conectividad sin DNS."""
    import socket
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, 53))
        return True
    except OSError:
        return False


def _enviar_batch(pendientes, endpoint, token):
    """
    Envía un batch de reproducciones al servidor.
    Retorna set de IDs enviados exitosamente.
    """
    payload = []
    id_map  = {}  # idempotency_key -> db_id

    for row in pendientes:
        db_id, ikey, timestamp, id_local, fuente, contenido, duracion, isrc, intentos = row
        payload.append({
            "idempotency_key": ikey,
            "timestamp":       timestamp,
            "id_local":        id_local,
            "fuente":          fuente,
            "contenido":       contenido,
            "duracion":        duracion,
            "isrc":            isrc,
        })
        id_map[ikey] = db_id

    body = json.dumps({"plays": payload}).encode("utf-8")
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent":    "CPMTracks-Agent/1.0",
    }

    try:
        req  = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        resp = urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT)
        data = json.loads(resp.read().decode())

        # El servidor responde {"accepted": ["key1","key2",...]}
        accepted = set(data.get("accepted", []))
        enviados = set()
        for ikey in accepted:
            if ikey in id_map:
                database.marcar_enviado(id_map[ikey])
                enviados.add(id_map[ikey])

        # Si el servidor no implementa "accepted" aún, marcamos todos
        if not accepted and resp.status in (200, 201, 202):
            for db_id in id_map.values():
                database.marcar_enviado(db_id)
                enviados.add(db_id)

        log.info(f"[SYNC] Enviados {len(enviados)}/{len(pendientes)} registros")
        return enviados

    except urllib.error.HTTPError as e:
        log.warning(f"[SYNC] HTTP {e.code}: {e.reason}")
        # 409 Conflict = duplicado en servidor → marcar como enviado igual
        if e.code == 409:
            for db_id in id_map.values():
                database.marcar_enviado(db_id)
        else:
            for row in pendientes:
                database.incrementar_intentos(row[0])
        return set()

    except Exception as e:
        log.warning(f"[SYNC] Error de red: {e}")
        for row in pendientes:
            database.incrementar_intentos(row[0])
        return set()


class SyncEngine(threading.Thread):
    """
    Hilo daemon que chequea conexión y envía cola pendiente periódicamente.
    """
    def __init__(self):
        super().__init__(daemon=True)
        self.name = "SyncEngine"
        self._stop_event = threading.Event()
        self.conectado   = False
        self.ultimo_sync = 0
        self.pendientes  = 0

    def run(self):
        log.info("[SYNC] Motor iniciado")
        while not self._stop_event.is_set():
            cfg = config.cargar()
            intervalo = cfg.get("sync_intervalo", 30)

            self.conectado  = _hay_internet()
            self.pendientes = database.contar_pendientes()

            if self.conectado and self.pendientes > 0:
                endpoint = cfg.get("api_endpoint", "")
                token    = cfg.get("api_token", "")
                if endpoint and token:
                    pendientes = database.obtener_pendientes(limite=200)
                    if pendientes:
                        _enviar_batch(pendientes, endpoint, token)
                        self.pendientes = database.contar_pendientes()
                        self.ultimo_sync = time.time()
                else:
                    log.debug("[SYNC] Sin endpoint/token configurado")

            self._stop_event.wait(intervalo)

    def _sincronizar_ahora(self):
        """Fuerza sincronizacion inmediata."""
        from core import config, database
        cfg      = config.cargar()
        endpoint = cfg.get("api_endpoint", "")
        token    = cfg.get("api_token", "")
        if not endpoint or not _hay_internet():
            return
        pendientes = database.obtener_pendientes(100)
        if pendientes:
            aceptados = _enviar_batch(pendientes, endpoint, token)
            for pid in aceptados:
                database.marcar_enviado(pid)

    def stop(self):
        self._stop_event.set()

    @property
    def estado(self):
        if not self.conectado:
            p = self.pendientes
            return ("sin_internet", f"{p} pendiente{'s' if p != 1 else ''}" if p > 0 else "sin conexión")
        if self.pendientes == 0:
            return ("ok", "sincronizado")
        return ("sincronizando", f"enviando {self.pendientes}...")
