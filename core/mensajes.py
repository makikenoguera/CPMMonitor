"""
CPM Tracks - Motor de mensajes push
Obtiene mensajes pendientes del servidor y los marca como leídos.
"""
import logging
import urllib.request
import urllib.error
import json
import ssl

log = logging.getLogger("mensajes")

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _get_base_and_token():
    from core.config import cargar
    cfg = cargar()
    base = cfg.get("api_endpoint", "").replace("/v1/plays", "")
    token = cfg.get("api_token", "")
    return base, token


class MensajesEngine:
    def obtener_pendientes(self):
        base, token = _get_base_and_token()
        if not base or not token:
            return []
        try:
            req = urllib.request.Request(
                f"{base}/mensajes",
                headers={"X-Token": token}
            )
            resp = urllib.request.urlopen(req, timeout=10, context=_SSL)
            return json.loads(resp.read().decode()).get("mensajes", [])
        except Exception as e:
            log.warning(f"Error obteniendo mensajes: {e}")
            return []

    def marcar_leido(self, mensaje_id):
        base, token = _get_base_and_token()
        if not base or not token:
            return
        try:
            req = urllib.request.Request(
                f"{base}/mensajes/{mensaje_id}/leer",
                data=b"{}",
                headers={"X-Token": token, "Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10, context=_SSL)
            log.info(f"Mensaje {mensaje_id} marcado como leído")
        except Exception as e:
            log.warning(f"Error marcando leído {mensaje_id}: {e}")
