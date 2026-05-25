"""
CPM Tracks - Scanner de fuentes de audio para Windows
Detecta reproducciones en Spotify, YouTube (Chrome/Edge/Firefox), VLC y otros.
Usa títulos de ventana vía ctypes win32 API.
"""
import ctypes
import ctypes.wintypes
import re
import logging
import time

log = logging.getLogger("scanner_win")

_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

def _get_window_titles():
    """Retorna lista de (hwnd, title, pid) de todas las ventanas visibles."""
    results = []
    def _cb(hwnd, _):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    pid = ctypes.wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    results.append((hwnd, title, pid.value))
        return True
    ctypes.windll.user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    return results


def _get_process_name(pid):
    """Retorna el nombre del ejecutable de un proceso dado su PID."""
    try:
        PROCESS_QUERY_LIMITED = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            return ""
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        ctypes.windll.kernel32.CloseHandle(h)
        import os
        return os.path.basename(buf.value).lower()
    except Exception:
        return ""


# ── SPOTIFY ──────────────────────────────────────────────────────────────────
# Spotify en Windows pone el título como "Artista - Canción" cuando reproduce
# y "Spotify Premium" o "Spotify" cuando está pausado/libre.
_SPOTIFY_EXES = {"spotify.exe"}

def _scan_spotify(windows):
    for hwnd, title, pid in windows:
        proc = _get_process_name(pid)
        if proc not in _SPOTIFY_EXES:
            continue
        # Cuando reproduce: "Artista - Canción" o "Artista – Canción"
        # Cuando pausa/libre: "Spotify" / "Spotify Premium" / "Spotify Free"
        if title.lower() in ("spotify", "spotify premium", "spotify free", ""):
            continue
        # Separador puede ser " - " o " – " (guión largo)
        for sep in (" – ", " - "):
            if sep in title:
                parts = title.split(sep, 1)
                artista = parts[0].strip()
                cancion = parts[1].strip()
                contenido = f"{artista} - {cancion}"
                return {
                    "fuente": "Spotify",
                    "contenido": contenido,
                    "duracion_seg": 0,
                    "isrc": "",
                }
        # Sin separador claro pero tiene título: mostrar como está
        if len(title) > 3:
            return {
                "fuente": "Spotify",
                "contenido": title,
                "duracion_seg": 0,
                "isrc": "",
            }
    return None


# ── YOUTUBE (Chrome / Edge / Firefox) ────────────────────────────────────────
_BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
_YT_SUFFIXES  = (" - youtube", " - youtube music")

def _scan_youtube(windows):
    for hwnd, title, pid in windows:
        proc = _get_process_name(pid)
        if proc not in _BROWSER_EXES:
            continue
        tl = title.lower()
        for suf in _YT_SUFFIXES:
            if tl.endswith(suf):
                cancion = title[:len(title) - len(suf)].strip()
                if cancion:
                    return {
                        "fuente": "YouTube",
                        "contenido": cancion,
                        "duracion_seg": 0,
                        "isrc": "",
                    }
    return None


# ── VLC ───────────────────────────────────────────────────────────────────────
# VLC: "Artista - Canción - VLC media player"
_VLC_SUFFIX = " - vlc media player"

def _scan_vlc(windows):
    for hwnd, title, pid in windows:
        proc = _get_process_name(pid)
        if proc != "vlc.exe":
            continue
        tl = title.lower()
        if tl == "vlc media player" or not tl.endswith(_VLC_SUFFIX):
            continue
        contenido = title[:len(title) - len(_VLC_SUFFIX)].strip()
        if contenido:
            return {
                "fuente": "Local (VLC)",
                "contenido": contenido,
                "duracion_seg": 0,
                "isrc": "",
            }
    return None


# ── WINDOWS MEDIA PLAYER ──────────────────────────────────────────────────────
_WMP_SUFFIX = " - windows media player"

def _scan_wmp(windows):
    for hwnd, title, pid in windows:
        proc = _get_process_name(pid)
        if proc not in ("wmplayer.exe", "mediaplayer.exe"):
            continue
        tl = title.lower()
        if not tl.endswith(_WMP_SUFFIX):
            continue
        contenido = title[:len(title) - len(_WMP_SUFFIX)].strip()
        if contenido:
            return {
                "fuente": "Local (WMP)",
                "contenido": contenido,
                "duracion_seg": 0,
                "isrc": "",
            }
    return None


# ── APPLE MUSIC / ITUNES ──────────────────────────────────────────────────────
_ITUNES_EXES = {"itunes.exe", "applemusic.exe"}
_ITUNES_SUFFIX = " - itunes"

def _scan_itunes(windows):
    for hwnd, title, pid in windows:
        proc = _get_process_name(pid)
        if proc not in _ITUNES_EXES:
            continue
        tl = title.lower()
        if tl in ("itunes", "apple music", ""):
            continue
        if tl.endswith(_ITUNES_SUFFIX):
            contenido = title[:len(title) - len(_ITUNES_SUFFIX)].strip()
        else:
            contenido = title
        if contenido:
            return {
                "fuente": "Apple Music",
                "contenido": contenido,
                "duracion_seg": 0,
                "isrc": "",
            }
    return None


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def escanear():
    """Escanea fuentes activas. Retorna dict o None."""
    try:
        windows = _get_window_titles()
        for fn in (_scan_spotify, _scan_youtube, _scan_vlc, _scan_itunes, _scan_wmp):
            result = fn(windows)
            if result:
                return result
    except Exception as e:
        log.warning(f"Scanner error: {e}")
    return None
