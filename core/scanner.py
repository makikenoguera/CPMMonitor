"""
CPM Tracks - Scanner de fuentes de audio
Detecta reproducciones en Spotify, Apple Music, QuickTime, VLC y YouTube/Chrome.
Retorna dict con fuente, contenido, duracion_seg, isrc o None si no hay nada.
"""
import subprocess
import logging

log = logging.getLogger("scanner")


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
        return (artist of t) & " - " & (name of t) & "||" & (duration of t) & "||" & (id of t)
    end tell
    '''
    res = _osascript(script)
    if not res or "||" not in res:
        return None
    parts = res.split("||")
    if len(parts) < 3:
        return None
    try:
        track_id = parts[2].split(":")[-1].strip()
        # Intentar obtener ISRC real via Spotify Web API
        try:
            from core.spotify_api import get_isrc
            isrc = get_isrc(track_id) or track_id
        except Exception:
            isrc = track_id
        return {
            "fuente":       "Spotify",
            "contenido":    parts[0].strip(),
            "duracion_seg": float(parts[1]) / 1000,
            "isrc":         isrc,
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
        titulo = res.replace(" - YouTube", "").strip()
        if titulo:
            return {
                "fuente":       "YouTube",
                "contenido":    titulo,
                "duracion_seg": 0,
                "isrc":         "N/A",
            }
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
        titulo = res.replace(" - YouTube", "").strip()
        if titulo:
            return {
                "fuente":       "YouTube (Safari)",
                "contenido":    titulo,
                "duracion_seg": 0,
                "isrc":         "N/A",
            }
    return None


# Orden de prioridad: streaming > local > web
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
    Ejecuta todos los scanners en orden de prioridad.
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
