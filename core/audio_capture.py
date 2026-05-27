"""
CPM Tracks — Captura de audio del sistema

Prioridad de dispositivo:
  Mac    : 1) BlackHole 2ch (loopback, calidad perfecta)
           2) Micrófono del sistema (fallback transparente)
  Windows: 1) WASAPI Loopback (nativo, sin drivers)
           2) Micrófono del sistema (fallback)

El usuario no necesita configurar nada — la app detecta automáticamente
lo que está disponible y usa el mejor dispositivo posible.

── Hoja de ruta ──────────────────────────────────────────────────────────────
  v4.x  : BlackHole (si instalado) → micrófono fallback       ← AQUÍ ESTAMOS
  v5.0  : BlackHole embebido en el instalador .pkg             ← próximo
  v5.x  : ScreenCaptureKit (macOS 13+, sin driver externo)    ← futuro
──────────────────────────────────────────────────────────────────────────────
"""
import sounddevice as sd
import numpy as np
import wave
import tempfile
import os
import platform
import logging

log = logging.getLogger("audio_capture")

DURATION_SEC = 10    # segundos a capturar por defecto
CHANNELS     = 2
_SILENCE_THR = 100   # amplitud mínima para considerar que hay señal


# ── Detección de dispositivos ─────────────────────────────────────────────────

def _find_loopback_device():
    """
    Busca el mejor dispositivo de loopback disponible.
    Mac    → BlackHole 2ch
    Windows → primer dispositivo WASAPI Loopback
    Retorna (device_idx, samplerate) o (None, None).
    """
    system  = platform.system()
    devices = sd.query_devices()

    for i, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        name = d["name"]
        if system == "Darwin"  and "BlackHole" in name:
            return i, int(d["default_samplerate"])
        if system == "Windows" and "Loopback" in name:
            return i, int(d["default_samplerate"])

    return None, None


def _find_mic_device():
    """
    Retorna el dispositivo de entrada por defecto del sistema (micrófono).
    Funciona en Mac y Windows sin ninguna instalación adicional.
    Retorna (device_idx, samplerate).
    """
    try:
        idx  = sd.default.device[0]   # índice del input por defecto
        info = sd.query_devices(idx)
        sr   = int(info.get("default_samplerate", 44100))
        return idx, sr
    except Exception:
        return None, 44100


def get_capture_info() -> dict:
    """
    Retorna información sobre el dispositivo que se usará para capturar.
    Útil para mostrar en el panel de configuración.
    """
    lb_idx, lb_sr = _find_loopback_device()
    if lb_idx is not None:
        d = sd.query_devices(lb_idx)
        return {"tipo": "loopback", "nombre": d["name"], "samplerate": lb_sr}

    mic_idx, mic_sr = _find_mic_device()
    if mic_idx is not None:
        d = sd.query_devices(mic_idx)
        return {"tipo": "microfono", "nombre": d["name"], "samplerate": mic_sr}

    return {"tipo": "ninguno", "nombre": "No disponible", "samplerate": 0}


# ── Captura ───────────────────────────────────────────────────────────────────

def _record(device_idx: int, samplerate: int, duration: int) -> np.ndarray | None:
    """Graba `duration` segundos desde `device_idx`. Retorna array int16 o None."""
    try:
        audio = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=CHANNELS,
            dtype="int16",
            device=device_idx,
        )
        sd.wait()
        return audio
    except Exception as e:
        log.warning(f"Error grabando desde device {device_idx}: {e}")
        return None


def capture_system_audio(duration: int = DURATION_SEC) -> str | None:
    """
    Captura `duration` segundos de audio.

    Intenta en este orden:
      1. BlackHole / WASAPI Loopback  (calidad perfecta)
      2. Micrófono del sistema        (fallback transparente)

    Retorna la ruta al archivo WAV temporal o None si no hay audio.
    El llamador es responsable de borrar el archivo.
    """
    audio      = None
    samplerate = 44100
    fuente     = "desconocida"

    # Intento 1: loopback
    lb_idx, lb_sr = _find_loopback_device()
    if lb_idx is not None:
        log.debug(f"Capturando desde loopback (device {lb_idx}) @ {lb_sr}Hz")
        audio      = _record(lb_idx, lb_sr, duration)
        samplerate = lb_sr
        fuente     = "loopback"

    # Intento 2: micrófono
    if audio is None or np.max(np.abs(audio)) < _SILENCE_THR:
        mic_idx, mic_sr = _find_mic_device()
        if mic_idx is not None:
            log.debug(f"Capturando desde micrófono (device {mic_idx}) @ {mic_sr}Hz")
            audio      = _record(mic_idx, mic_sr, duration)
            samplerate = mic_sr
            fuente     = "microfono"

    if audio is None:
        log.warning("No se encontró ningún dispositivo de audio")
        return None

    # Verificar señal
    if np.max(np.abs(audio)) < _SILENCE_THR:
        log.debug(f"Audio capturado ({fuente}) es silencio — nada reproduciéndose")
        return None

    # Guardar WAV temporal
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(audio.tobytes())
        log.debug(f"WAV guardado ({fuente}): {tmp.name}")
        return tmp.name
    except Exception as e:
        log.warning(f"Error guardando WAV: {e}")
        return None
