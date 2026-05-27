"""
CPM Tracks - Scanner de fuentes de audio
Detecta reproducciones en Spotify, Apple Music, QuickTime, VLC y YouTube/Chrome.
Retorna dict con fuente, contenido, duracion_seg, isrc o None si no hay nada.

── Estrategia sin micrófono ─────────────────────────────────────────────────
  Spotify / Apple Music  → AppleScript → ISRC via MusicBrainz
  YouTube (Chrome/Safari)→ título de pestaña → parse "Artista - Título"
                           → ISRC via MusicBrainz (caché, sin repetir búsqueda)
  ACRCloud               → desactivado del scan automático (requiere micrófono)
─────────────────────────────────────────────────────────────────────────────
"""
import subprocess
import logging
import re

log = logging.getLogger("scanner")

# Regex para limpiar prefijos de notificación de browser: "(206) Título" → "Título"
_RE_NOTIF = re.compile(r'^\(\d+\)\s*')

# Sufijos comunes en títulos de YouTube que no son parte del nombre de la canción
_RE_YT_SUFFIX = re.compile(
    r'\s*[\(\[](Official\s*(Video|Audio|Music\s*Video|Lyric\s*Video|Clip)|'
    r'Video\s*Oficial|Letra|Lyrics|HD|4K|HQ|En\s*Vivo|Live|Visualizer|'
    r'Lyric\s*Video|Performance\s*Video)[\)\]]\s*',
    re.IGNORECASE
)


def _osascript(script, timeout=2):
    """Ejecuta un script AppleScript y retorna el resultado limpio o None."""
    try:
        result = subprocess.check_output(
            ['osascript', '-e', script],
            timeout=timeout,
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        return result if result else None
    except Exception:
        return None


def _scan_spotify():
    script = '''
    tell application "System Events"
        if (count of (every process whose name is "Spotify")) = 0 then return ""
    end tell
    tell application "Spotify"
        if player state is not playing then return ""
        set t to current track
        return (artist of t) & tab & (name of t) & "||" & (duration of t) & "||" & (id of t)
    end tell
    '''
    res = _osascript(script)
    if not res or "||" not in res:
        return None
    parts = res.split("||")
    if len(parts) < 3:
        return None
    try:
        # parts[0] = "artista|||titulo", parts[1] = duration ms, parts[2] = spotify:track:ID
        art_tit = parts[0].split("\t", 1)
        artista = art_tit[0].strip()
        titulo  = art_tit[1].strip() if len(art_tit) > 1 else artista
        contenido = f"{artista} - {titulo}"
        track_id  = parts[2].split(":")[-1].strip()

        # ISRC via MusicBrainz (gratuito, sin suscripción)
        try:
            from core.musicbrainz_api import get_isrc as mb_isrc
            isrc = mb_isrc(artista, titulo) or track_id
        except Exception:
            isrc = track_id

        return {
            "fuente":           "Spotify",
            "contenido":        contenido,
            "artista":          artista,
            "titulo":           titulo,
            "duracion_seg":     float(parts[1]) / 1000,
            "isrc":             isrc,
            "spotify_track_id": track_id,
        }
    except (ValueError, IndexError):
        return None


def _scan_apple_music():
    script = '''
    tell application "System Events"
        if (count of (every process whose name is "Music")) = 0 then return ""
    end tell
    tell application "Music"
        if player state is not playing then return ""
        set t to current track
        return (artist of t) & " - " & (name of t) & "||" & (duration of t) & "||" & (comment of t)
    end tell
    '''
    res = _osascript(script)
    if not res or "||" not in res:
        return None
    parts = res.split("||")
    if len(parts) < 2:
        return None
    try:
        isrc = parts[2].strip() if len(parts) > 2 and parts[2].strip() else "APPLE_MUSIC"
        return {
            "fuente":       "Apple Music",
            "contenido":    parts[0].strip(),
            "duracion_seg": float(parts[1]),
            "isrc":         isrc,
        }
    except (ValueError, IndexError):
        return None


def _scan_quicktime():
    script = '''
    tell application "System Events"
        if (count of (every process whose name is "QuickTime Player")) = 0 then return ""
    end tell
    tell application "QuickTime Player"
        if (count of documents) = 0 then return ""
        if playing of document 1 is false then return ""
        return (name of document 1) & "||" & (duration of document 1)
    end tell
    '''
    res = _osascript(script)
    if not res or "||" not in res:
        return None
    parts = res.split("||")
    try:
        return {
            "fuente":       "Local (QuickTime)",
            "contenido":    parts[0].strip(),
            "duracion_seg": float(parts[1]),
            "isrc":         "LOCAL",
        }
    except (ValueError, IndexError):
        return None


def _scan_vlc():
    script = '''
    tell application "System Events"
        if (count of (every process whose name is "VLC")) = 0 then return ""
    end tell
    tell application "VLC"
        if playing then
            return (get name of current item) & "||" & (get duration)
        end if
        return ""
    end tell
    '''
    res = _osascript(script)
    if not res or "||" not in res:
        return None
    parts = res.split("||")
    try:
        return {
            "fuente":       "Local (VLC)",
            "contenido":    parts[0].strip(),
            "duracion_seg": float(parts[1]),
            "isrc":         "LOCAL",
        }
    except (ValueError, IndexError):
        return None


def _parse_youtube_title(raw_title: str) -> dict:
    """
    Parsea un título de YouTube y busca ISRC en MusicBrainz.

    Patrones soportados:
      "KAROL G - PROVENZA (Official Video)"  → artista=KAROL G, titulo=PROVENZA
      "PROVENZA - KAROL G"                   → artista=KAROL G, titulo=PROVENZA
      "PROVENZA"                             → solo titulo, sin artista

    Retorna dict con contenido, artista, titulo, isrc.
    """
    # 1. Limpiar sufijos de YouTube y notificaciones
    clean = _RE_NOTIF.sub('', raw_title)
    clean = _RE_YT_SUFFIX.sub('', clean).strip()

    artista = ""
    titulo  = clean
    isrc    = "N/A"

    # 2. Intentar split "Artista - Título"
    if " - " in clean:
        parts   = clean.split(" - ", 1)
        artista = parts[0].strip()
        titulo  = parts[1].strip()

    # 3. Buscar ISRC en MusicBrainz (caché → solo 1 petición por canción)
    if artista and titulo:
        try:
            from core.musicbrainz_api import get_isrc as mb_isrc
            found = mb_isrc(artista, titulo)
            if found:
                isrc = found
        except Exception:
            pass

    return {
        "contenido": clean,          # título limpio completo (para mostrar)
        "artista":   artista,
        "titulo":    titulo,
        "isrc":      isrc,
    }


def _scan_youtube_chrome():
    script = '''
    tell application "System Events"
        if (count of (every process whose name is "Google Chrome")) = 0 then return ""
    end tell
    tell application "Google Chrome"
        if (count of windows) = 0 then return ""
        return title of active tab of first window
    end tell
    '''
    res = _osascript(script)
    if not res:
        return None
    if "YouTube" in res and res != "YouTube":
        raw = res.replace(" - YouTube", "").strip()
        if raw:
            info = _parse_youtube_title(raw)
            return {"fuente": "YouTube", "duracion_seg": 0, **info}
    return None


def _scan_youtube_safari():
    script = '''
    tell application "System Events"
        if (count of (every process whose name is "Safari")) = 0 then return ""
    end tell
    tell application "Safari"
        if (count of windows) = 0 then return ""
        return name of current tab of first window
    end tell
    '''
    res = _osascript(script)
    if not res:
        return None
    if "YouTube" in res and res != "YouTube":
        raw = res.replace(" - YouTube", "").strip()
        if raw:
            info = _parse_youtube_title(raw)
            return {"fuente": "YouTube (Safari)", "duracion_seg": 0, **info}
    return None


# ACRCloud disponible como función standalone (para botón manual futuro)
# NO incluido en _SCANNERS — requiere micrófono, intrusivo para el usuario
def identify_with_acrcloud(duration: int = 10):
    """Identificación manual por huella acústica. No se llama automáticamente."""
    try:
        from core.acrcloud_api import identify_system_audio
        return identify_system_audio(duration=duration)
    except Exception as e:
        log.debug(f"ACRCloud manual error: {e}")
        return None


# Orden de prioridad — todos sin micrófono, respuesta instantánea
_SCANNERS = [
    _scan_spotify,
    _scan_apple_music,
    _scan_quicktime,
    _scan_vlc,
    _scan_youtube_chrome,
    _scan_youtube_safari,
]


def escanear():
    """
    Ejecuta los scanners en orden de prioridad.
    Retorna el primer resultado válido o None.
    """
    for scanner in _SCANNERS:
        try:
            resultado = scanner()
            if resultado:
                return resultado
        except Exception as e:
            log.debug(f"Scanner {scanner.__name__} error: {e}")
    return None
