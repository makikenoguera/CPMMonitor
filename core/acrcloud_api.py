"""
CPM Tracks — ACRCloud audio recognition
Identifica canciones a partir de audio capturado del sistema.
Usa HMAC-SHA1 para autenticación. Sin dependencias externas.
Retorna dict con artista, titulo, isrc o None.
"""
import base64
import hashlib
import hmac
import time
import ssl
import json
import logging
import urllib.request
import os

log = logging.getLogger("acrcloud")


def _get_config():
    try:
        from core.config import cargar
        cfg = cargar()
        return (
            cfg.get("acrcloud_host", ""),
            cfg.get("acrcloud_key", ""),
            cfg.get("acrcloud_secret", ""),
        )
    except Exception:
        return (
            os.environ.get("ACRCLOUD_HOST", ""),
            os.environ.get("ACRCLOUD_KEY", ""),
            os.environ.get("ACRCLOUD_SECRET", ""),
        )


def _ssl_ctx():
    ctx = ssl.create_default_context()
    try:
        import certifi
        ca = certifi.where()
        if os.path.exists(ca):
            return ssl.create_default_context(cafile=ca)
    except Exception:
        pass
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_multipart(fields: dict, file_bytes: bytes, boundary: str) -> bytes:
    """Construye el cuerpo multipart/form-data manualmente."""
    parts = []
    crlf = b"\r\n"
    sep  = f"--{boundary}".encode()

    for name, value in fields.items():
        parts += [
            sep, crlf,
            f'Content-Disposition: form-data; name="{name}"'.encode(), crlf,
            crlf,
            str(value).encode(), crlf,
        ]

    # El archivo de audio
    parts += [
        sep, crlf,
        b'Content-Disposition: form-data; name="sample"; filename="audio.wav"', crlf,
        b"Content-Type: audio/wav", crlf,
        crlf,
        file_bytes, crlf,
    ]

    parts += [f"--{boundary}--".encode(), crlf]
    return b"".join(parts)


def identify_file(wav_path: str) -> dict | None:
    """
    Envía un archivo WAV a ACRCloud y retorna los metadatos de la canción.
    Retorna dict con fuente, contenido, artista, titulo, isrc o None.
    """
    host, key, secret = _get_config()
    if not host or not key or not secret:
        log.warning("ACRCloud no configurado (faltan host/key/secret)")
        return None

    try:
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as e:
        log.warning(f"No se pudo leer {wav_path}: {e}")
        return None
    finally:
        try:
            os.unlink(wav_path)
        except Exception:
            pass

    # Firma HMAC-SHA1
    http_method      = "POST"
    http_uri         = "/v1/identify"
    data_type        = "audio"
    sig_version      = "1"
    timestamp        = str(int(time.time()))
    string_to_sign   = "\n".join([http_method, http_uri, key, data_type, sig_version, timestamp])
    signature        = base64.b64encode(
        hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()

    fields = {
        "access_key":       key,
        "data_type":        data_type,
        "signature_version": sig_version,
        "signature":        signature,
        "sample_bytes":     len(audio_bytes),
        "timestamp":        timestamp,
    }

    boundary = "CPMMonitorBoundary7x"
    body     = _build_multipart(fields, audio_bytes, boundary)

    url = f"https://{host}{http_uri}"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        resp = urllib.request.urlopen(req, timeout=15, context=_ssl_ctx())
        data = json.loads(resp.read().decode())
    except Exception as e:
        log.warning(f"ACRCloud request error: {e}")
        return None

    status_code = data.get("status", {}).get("code", -1)
    if status_code != 0:
        msg = data.get("status", {}).get("msg", "")
        log.debug(f"ACRCloud sin resultado: {status_code} — {msg}")
        return None

    # Extraer metadata del primer resultado
    try:
        music   = data["metadata"]["music"][0]
        artista = music.get("artists", [{}])[0].get("name", "").strip()
        titulo  = music.get("title", "").strip()
        album   = music.get("album", {}).get("name", "")
        isrc    = music.get("external_ids", {}).get("isrc", "") or \
                  music.get("external_ids", {}).get("ISRC", "") or "N/A"
        score   = music.get("score", 0)

        log.info(f"ACRCloud: {artista} - {titulo} | ISRC: {isrc} | score: {score}")

        return {
            "fuente":       "Audio (ACRCloud)",
            "contenido":    f"{artista} - {titulo}" if artista else titulo,
            "artista":      artista,
            "titulo":       titulo,
            "album":        album,
            "duracion_seg": 0,
            "isrc":         isrc,
            "acr_score":    score,
        }
    except (KeyError, IndexError) as e:
        log.warning(f"ACRCloud parse error: {e} — {data}")
        return None


def identify_system_audio(duration: int = 10) -> dict | None:
    """Captura audio del sistema e identifica con ACRCloud."""
    try:
        from core.audio_capture import capture_system_audio
        wav_path = capture_system_audio(duration)
        if not wav_path:
            return None
        return identify_file(wav_path)
    except Exception as e:
        log.warning(f"identify_system_audio error: {e}")
        return None
