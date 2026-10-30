import logging
import threading
import time
from collections import deque
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class AudioCaptureManager:
    SAMPLE_RATE = 44100
    CHANNELS = 1
    BUFFER_SECONDS = 60
    # Chunk size in frames per read call
    CHUNK_FRAMES = 4096

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Circular buffer as a deque of numpy chunks
        self._chunks: deque = deque()
        self._total_samples: int = 0
        self._max_samples: int = self.SAMPLE_RATE * self.BUFFER_SECONDS
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._audio_detected_at: float = 0.0
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._record_loop, daemon=True, name='AudioCapture')
        self._thread.start()
        logger.info("AudioCaptureManager: started")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("AudioCaptureManager: stopped")

    @property
    def current_rms(self) -> float:
        """RMS of the last 0.5 seconds of buffered audio."""
        samples = self._get_last_n_samples(int(self.SAMPLE_RATE * 0.5))
        if samples is None or len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

    def capture_sample(self, seconds: float = 20.0) -> Optional[np.ndarray]:
        """Return the last `seconds` of buffered mono float32 audio, or None."""
        n = int(self.SAMPLE_RATE * seconds)
        samples = self._get_last_n_samples(n)
        if samples is None or len(samples) < n:
            return None
        return samples.astype(np.float32)

    def clear_buffer(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._total_samples = 0

    @property
    def audio_detected_at(self) -> float:
        """Unix timestamp when audio was first detected, or 0."""
        return self._audio_detected_at

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_loop(self) -> None:
        try:
            import soundcard as sc
        except ImportError:
            logger.error("AudioCaptureManager: soundcard library not available")
            return

        while not self._stop_event.is_set():
            try:
                # Get default loopback (WASAPI loopback on Windows)
                speaker = sc.default_speaker()
                mic = sc.get_microphone(
                    id=str(speaker.name),
                    include_loopback=True,
                )
                logger.info("AudioCaptureManager: using loopback device '%s'", mic.name)
                with mic.recorder(
                    samplerate=self.SAMPLE_RATE,
                    channels=self.CHANNELS,
                ) as recorder:
                    while not self._stop_event.is_set():
                        data = recorder.record(numframes=self.CHUNK_FRAMES)
                        # data shape: (frames, channels) → flatten to 1D
                        mono = data[:, 0] if data.ndim > 1 else data.ravel()
                        self._push_chunk(mono.astype(np.float32))
                        self._update_audio_detected(mono)
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("AudioCaptureManager: recording error (%s), retrying in 2s", exc)
                self._stop_event.wait(2)

    def _push_chunk(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._chunks.append(chunk)
            self._total_samples += len(chunk)
            # Trim oldest samples if over capacity
            while self._total_samples > self._max_samples and self._chunks:
                removed = self._chunks.popleft()
                self._total_samples -= len(removed)

    AUDIO_RMS_THRESHOLD: float = 0.001   # must match ScannerManager.AUDIO_THRESHOLD

    def _update_audio_detected(self, chunk: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        if rms > self.AUDIO_RMS_THRESHOLD:
            if self._audio_detected_at == 0.0:
                self._audio_detected_at = time.time()
        else:
            self._audio_detected_at = 0.0

    def _get_last_n_samples(self, n: int) -> Optional[np.ndarray]:
        with self._lock:
            if self._total_samples == 0:
                return None
            all_chunks = list(self._chunks)

        if not all_chunks:
            return None

        combined = np.concatenate(all_chunks)
        if len(combined) < n:
            return combined
        return combined[-n:]
