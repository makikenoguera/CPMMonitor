"""
CPM Tracks — Identificación de audio por huella acústica
Usa Chromaprint (fpcalc) + AcoustID API + MusicBrainz para obtener ISRC.
Flujo: WAV → fingerprint → AcoustID → MusicBrainz recording → ISRC
"""
import acoustid
import logging
import urllib.request
import json

log = logging.getLogger("fingerprint")

_cache = {}  # {fingerprint_hash: resultado}


def _get_api_key():
    try:
        from core.config import cargar
        return cargar().get("acoustid_api_key", "")
    except Exception:
        import os
        return os.environ.get("ACOUSTID_API_KEY", "")


def _isrc_from_mbid(mbid: str) -> str | None:
    """Consulta MusicBrainz para obtener el ISRC de un recording ID."""
    if not mbid:
        return None
    try:
        from core.musicbrainz_api import _ssl_ctx, _rate_limit, USER_AGENT
        _rate_limit()
        url = f"https://musicbrainz.org/ws/2/recording/{mbid}?inc=isrcs&fmt=json"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        resp = urllib.request.urlopen(req, timeout=8, context=_ssl_ctx())
        d = json.loads(resp.read().decode())
        isrcs = d.get("isrcs", [])
        return isrcs[0] if isrcs else None
    except Exception as e:
        log.warning(f"MusicBrainz MBID lookup error ({mbid}): {e}")
        return None


def identify_file(wav_path: str) -> dict | None:
    """
    Identifica una canción a partir de un archivo WAV.
    Retorna dict con fuente, contenido, artista, titulo, isrc, duracion_seg
    o None si no se pudo identificar.
    """
    api_key = _get_api_key()
    if not api_key:
        log.warning("Sin acoustid_api_key en config — fingerprinting desactivado")
        return None

    try:
        results = list(acoustid.match(api_key, wav_path))
    except acoustid.NoBackendError:
        log.error("fpcalc no encontrado — instala chromaprint: brew install chromaprint")
        return None
    except Exception as e:
        log.warning(f"AcoustID error: {e}")
        return None
    finally:
        # Limpiar archivo temporal
        try:
            import os
            os.unlink(wav_path)
        except Exception:
            pass

    if not results:
        log.debug("AcoustID: sin resultados")
        return None

    # El primer resultado es el de mayor score
    score, recording_id, title, artist = results[0]
    log.info(f"AcoustID match: score={score:.2f} | {artist} - {title} | mbid={recording_id}")

    if score < 0.5:
        log.debug(f"Score muy bajo ({score:.2f}) — descartando")
        return None

    artista = (artist or "").strip()
    titulo  = (title  or "").strip()

    # Obtener ISRC desde MusicBrainz
    isrc = _isrc_from_mbid(recording_id)

    # Fallback: buscar por artista+título
    if not isrc and artista and titulo:
        try:
            from core.musicbrainz_api import get_isrc as mb_isrc
            isrc = mb_isrc(artista, titulo)
        except Exception:
            pass

    isrc = isrc or "N/A"

    return {
        "fuente":       "Audio (fingerprint)",
        "contenido":    f"{artista} - {titulo}" if artista else titulo,
        "artista":      artista,
        "titulo":       titulo,
        "duracion_seg": 0,
        "isrc":         isrc,
        "fp_score":     round(score, 3),
    }


def identify_system_audio(duration: int = 12) -> dict | None:
    """
    Captura audio del sistema e intenta identificarlo.
    Shortcut: audio_capture → identify_file.
    Retorna mismo dict que identify_file o None.
    """
    try:
        from core.audio_capture import capture_system_audio
        wav_path = capture_system_audio(duration)
        if not wav_path:
            return None
        return identify_file(wav_path)
    except Exception as e:
        log.warning(f"identify_system_audio error: {e}")
        return None
