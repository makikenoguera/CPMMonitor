"""
CPM Tracks — Captura de audio del sistema
Mac:     BlackHole 2ch (requiere Multi-Output Device configurado)
Windows: WASAPI Loopback (nativo, sin drivers adicionales)
Retorna ruta a archivo WAV temporal o None si no hay dispositivo.
"""
import sounddevice as sd
import numpy as np
import wave
import tempfile
import os
import platform
import logging

log = logging.getLogger("audio_capture")

DURATION_SEC  = 12     # segundos a capturar
CHANNELS      = 2
SAMPLE_RATE   = 44100  # Hz (fallback; se usa el nativo del dispositivo)


def _find_loopback_device():
    """
    Encuentra el índice del dispositivo de loopback según el SO.
    Mac    → BlackHole 2ch
    Windows → primer dispositivo con 'Loopback' en el nombre
    Retorna (device_idx, sample_rate) o (None, None).
    """
    system = platform.system()
    devices = sd.query_devices()

    for i, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        name = d["name"]
        if system == "Darwin" and "BlackHole" in name:
            return i, int(d["default_samplerate"])
        if system == "Windows" and "Loopback" in name:
            return i, int(d["default_samplerate"])

    log.warning("No se encontró dispositivo de loopback (BlackHole / WASAPI Loopback)")
    return None, None


def capture_system_audio(duration=DURATION_SEC) -> str | None:
    """
    Graba `duration` segundos del audio del sistema.
    Retorna la ruta al archivo WAV temporal (el llamador debe borrarlo).
    Retorna None si no hay dispositivo de loopback disponible.
    """
    device_idx, samplerate = _find_loopback_device()
    if device_idx is None:
        return None

    samplerate = samplerate or SAMPLE_RATE
    log.debug(f"Capturando {duration}s desde device {device_idx} @ {samplerate}Hz")

    try:
        audio = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=CHANNELS,
            dtype="int16",
            device=device_idx,
        )
        sd.wait()

        # Verificar que hay señal (no silencio total)
        if np.max(np.abs(audio)) < 100:
            log.debug("Audio capturado es silencio — nada reproduciéndose")
            return None

        # Guardar WAV temporal
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)       # int16 = 2 bytes
            wf.setframerate(samplerate)
            wf.writeframes(audio.tobytes())

        log.debug(f"WAV guardado: {tmp.name}")
        return tmp.name

    except Exception as e:
        log.warning(f"Error capturando audio: {e}")
        return None
