import json
import logging
import os
import subprocess
import sys
import tempfile
import wave
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _fpcalc_path() -> str:
    """Resolve path to fpcalc.exe, supporting PyInstaller bundles."""
    # PyInstaller extracted directory
    if hasattr(sys, '_MEIPASS'):
        candidate = os.path.join(sys._MEIPASS, 'fpcalc.exe')
        if os.path.isfile(candidate):
            return candidate

    # Same directory as the frozen executable
    if getattr(sys, 'frozen', False):
        candidate = os.path.join(os.path.dirname(sys.executable), 'fpcalc.exe')
        if os.path.isfile(candidate):
            return candidate

    # Development: same directory as this file
    candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fpcalc.exe')
    candidate = os.path.normpath(candidate)
    if os.path.isfile(candidate):
        return candidate

    # Last resort: PATH
    return 'fpcalc.exe'


class FingerprintEngine:
    @staticmethod
    def is_available() -> bool:
        """Check if fpcalc.exe is reachable."""
        path = _fpcalc_path()
        if os.path.isfile(path):
            return True
        # Try launching from PATH
        try:
            result = subprocess.run(
                [path, '-version'],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def generate_raw(
        pcm_data: np.ndarray,
        sample_rate: int,
    ) -> Optional[dict]:
        """Generate a raw fingerprint from PCM audio data.

        Returns:
            {"values": [int32, ...], "duration": float} or None on failure.
        """
        if pcm_data is None or len(pcm_data) == 0:
            return None

        fpcalc = _fpcalc_path()

        # Write PCM to a temporary WAV file
        tmp_wav = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                tmp_wav = f.name

            _write_wav(tmp_wav, pcm_data, sample_rate)

            result = subprocess.run(
                [fpcalc, '-raw', '-json', tmp_wav],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace').strip()
                logger.warning("fpcalc error (rc=%d): %s", result.returncode, stderr)
                return None

            stdout = result.stdout.decode('utf-8', errors='replace').strip()
            data = json.loads(stdout)

            values = data.get('fingerprint', data.get('values', []))
            duration = float(data.get('duration', 0.0))

            if not values:
                logger.warning("fpcalc returned empty fingerprint")
                return None

            return {'values': values, 'duration': duration}

        except json.JSONDecodeError as exc:
            logger.error("fpcalc JSON parse error: %s", exc)
            return None
        except subprocess.TimeoutExpired:
            logger.error("fpcalc timed out")
            return None
        except Exception as exc:
            logger.error("FingerprintEngine.generate_raw error: %s", exc, exc_info=True)
            return None
        finally:
            if tmp_wav and os.path.exists(tmp_wav):
                try:
                    os.unlink(tmp_wav)
                except OSError:
                    pass


def _write_wav(path: str, pcm_data: np.ndarray, sample_rate: int) -> None:
    """Write mono float32 numpy array to a 16-bit PCM WAV file."""
    # Normalise to int16
    audio = pcm_data.astype(np.float32)
    # Clip to [-1, 1] to avoid overflow
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
