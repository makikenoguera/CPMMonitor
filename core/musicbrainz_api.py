"""
CPM Tracks — MusicBrainz API helper
Obtiene el ISRC real de una canción buscando por artista y título.
API pública, sin autenticación ni costo. Límite ~1 req/seg.
"""
import logging
import urllib.request
import urllib.parse
import json
import ssl
import time

log = logging.getLogger("musicbrainz")

# Caché en memoria: {(artista_lower, titulo_lower): isrc}
_cache = {}
_last_req = 0.0

USER_AGENT = "CPMMonitor/1.0 (contacto@cpmtracks.com)"


def _ssl_ctx():
    ctx = ssl.create_default_context()
    try:
        import certifi, os
        ca = certifi.where()
        if os.path.exists(ca):
            return ssl.create_default_context(cafile=ca)
    except Exception:
        pass
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _rate_limit():
    """Espera lo necesario para no superar 1 req/seg."""
    global _last_req
    elapsed = time.time() - _last_req
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    _last_req = time.time()


def get_isrc(artista: str, titulo: str) -> str | None:
    """
    Busca en MusicBrainz por artista y título.
    Retorna el primer ISRC encontrado o None.
    Usa caché en memoria para evitar búsquedas repetidas.
    """
    if not artista or not titulo:
        return None

    key = (artista.lower().strip(), titulo.lower().strip())
    if key in _cache:
        return _cache[key]

    _rate_limit()

    query = f'recording:"{titulo}" AND artistname:"{artista}"'
    url = "https://musicbrainz.org/ws/2/recording?" + urllib.parse.urlencode({
        "query": query,
        "fmt":   "json",
        "limit": 5,
        "inc":   "isrcs",
    })

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        resp = urllib.request.urlopen(req, timeout=8, context=_ssl_ctx())
        d = json.loads(resp.read().decode())

        for rec in d.get("recordings", []):
            isrcs = rec.get("isrcs", [])
            if isrcs:
                isrc = isrcs[0]
                _cache[key] = isrc
                log.info(f"MusicBrainz ISRC: {artista} – {titulo} → {isrc}")
                return isrc

        # Sin ISRC en MusicBrainz — guardamos None para no volver a buscar
        _cache[key] = None
        log.debug(f"MusicBrainz: sin ISRC para '{artista} – {titulo}'")
        return None

    except Exception as e:
        log.warning(f"MusicBrainz error ({artista} – {titulo}): {e}")
        return None
