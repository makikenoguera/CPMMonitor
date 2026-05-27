"""
CPM Tracks — Spotify Web API helper
Obtiene el ISRC real de una canción a partir del Spotify Track ID.
Requiere CLIENT_ID y CLIENT_SECRET en config.json o variables de entorno.
"""
import logging
import urllib.request
import urllib.parse
import json
import ssl
import time
import base64

log = logging.getLogger("spotify_api")

# Caché en memoria: {track_id: isrc}
_cache = {}
_token = None
_token_expires = 0


def _ssl():
    ctx = ssl.create_default_context()
    try:
        import certifi, os, sys
        ca = certifi.where()
        if not os.path.exists(ca) and hasattr(sys, '_MEIPASS'):
            ca = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
        if os.path.exists(ca):
            return ssl.create_default_context(cafile=ca)
    except Exception:
        pass
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get_credentials():
    try:
        from core.config import cargar
        cfg = cargar()
        cid = cfg.get("spotify_client_id", "") or ""
        sec = cfg.get("spotify_client_secret", "") or ""
        if not cid or not sec:
            import os
            cid = os.environ.get("SPOTIFY_CLIENT_ID", "")
            sec = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        return cid.strip(), sec.strip()
    except Exception:
        return "", ""


def _get_token():
    global _token, _token_expires
    if _token and time.time() < _token_expires - 60:
        return _token
    cid, sec = _get_credentials()
    if not cid or not sec:
        return None
    try:
        creds = base64.b64encode(f"{cid}:{sec}".encode()).decode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=b"grant_type=client_credentials",
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
        )
        resp = urllib.request.urlopen(req, timeout=5, context=_ssl())
        d = json.loads(resp.read().decode())
        _token = d.get("access_token")
        _token_expires = time.time() + d.get("expires_in", 3600)
        log.info("Spotify token renovado")
        return _token
    except Exception as e:
        log.warning(f"Error obteniendo token Spotify: {e}")
        return None


def get_isrc(spotify_track_id: str) -> str | None:
    """
    Dado un Spotify Track ID (ej: '6OGogr19zPTM4AfnP4d6pK'),
    retorna el ISRC real (ej: 'USUM72205907') o None si no se puede obtener.
    Usa caché en memoria para evitar llamadas repetidas.
    """
    if not spotify_track_id or spotify_track_id in ("N/A", "LOCAL", "APPLE_MUSIC"):
        return None
    # Ya está en caché
    if spotify_track_id in _cache:
        return _cache[spotify_track_id]
    token = _get_token()
    if not token:
        return None
    try:
        req = urllib.request.Request(
            f"https://api.spotify.com/v1/tracks/{spotify_track_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        resp = urllib.request.urlopen(req, timeout=5, context=_ssl())
        d = json.loads(resp.read().decode())
        isrc = d.get("external_ids", {}).get("isrc")
        if isrc:
            _cache[spotify_track_id] = isrc
            log.info(f"ISRC obtenido: {spotify_track_id} → {isrc}")
        return isrc
    except Exception as e:
        log.warning(f"Error obteniendo ISRC de Spotify ({spotify_track_id}): {e}")
        return None
