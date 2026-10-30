import datetime
import hashlib
import logging
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ScannerManager:
    """Port of the Swift ScannerManager.

    Detection pipeline:
    1. Every 2 seconds, check RMS of audio buffer.
    2. If audio above threshold, request a fingerprint + match.
    3. Require REQUIRED_CONFIRMATIONS consecutive identical matches before
       creating a candidate (anti-false-positive).
    4. Accumulate listening time while audio is present.
    5. Save a play when accumulated >= min_detection_time AND
       porcentaje >= umbral_porcentaje.
    6. Pre-credit time detected before identification (audioDetectedAt).
    """

    AUDIO_THRESHOLD: float = 0.001   # WASAPI loopback levels vary by device
    ACCUMULATION_INTERVAL: float = 2.0   # seconds between RMS ticks
    REQUIRED_CONFIRMATIONS: int = 2      # 2 consecutive matches required before confirming
    SAMPLE_SECONDS: int = 15             # 15s of audio is enough for Chromaprint
    MIN_QUERY_INTERVAL: float = 10.0     # query every 10s (was 20s — too slow)
    PERIODIC_CHECK_INTERVAL: float = 10.0

    def __init__(self, config, db, catalog, matcher, audio) -> None:
        self._config = config
        self._db = db
        self._catalog = catalog
        self._matcher = matcher
        self._audio = audio

        # Scanning state
        self._is_scanning: bool = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Debug / diagnostic
        self._rms_log_counter: int = 0

        # Candidate state
        self._candidate: Optional[dict[str, Any]] = None
        self._pending_match: Optional[dict[str, Any]] = None  # last match result
        self._confirmation_count: int = 0
        self._last_query_time: float = 0.0
        self._last_match_key: Optional[str] = None

        # Callback for status updates
        self.on_status_change: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_scanning(self) -> bool:
        return self._is_scanning

    @property
    def current_candidate(self) -> Optional[dict]:
        """Candidato activo (None si no hay canción identificada)."""
        return self._candidate

    @property
    def rms_level(self) -> float:
        """Nivel RMS actual del audio capturado."""
        return self._audio.current_rms

    def start(self) -> None:
        if self._is_scanning:
            return
        self._is_scanning = True
        self._stop_event.clear()
        self._audio.start()
        self._thread = threading.Thread(
            target=self._scan_loop,
            daemon=True,
            name='ScannerManager',
        )
        self._thread.start()
        logger.info("ScannerManager: started")
        self._notify_status("Escuchando...")

    def stop(self) -> None:
        if not self._is_scanning:
            return
        self._is_scanning = False
        self._stop_event.set()
        self._audio.stop()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        self._candidate = None
        self._confirmation_count = 0
        self._last_match_key = None
        self._pending_match = None
        logger.info("ScannerManager: stopped")
        self._notify_status("Detenido")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            tick_start = time.monotonic()

            try:
                self._tick()
            except Exception as exc:
                logger.error("ScannerManager._tick error: %s", exc, exc_info=True)

            elapsed = time.monotonic() - tick_start
            sleep_time = max(0.0, self.ACCUMULATION_INTERVAL - elapsed)
            self._stop_event.wait(sleep_time)

    def _tick(self) -> None:
        rms = self._audio.current_rms
        audio_active = rms >= self.AUDIO_THRESHOLD

        # Log RMS every ~30 ticks (60 seconds) so we can diagnose audio issues
        self._rms_log_counter += 1
        if self._rms_log_counter >= 30:
            self._rms_log_counter = 0
            logger.info(
                "ScannerManager: RMS=%.5f (threshold=%.4f) audio_active=%s candidate=%s",
                rms, self.AUDIO_THRESHOLD, audio_active,
                self._candidate.get('titulo', '?') if self._candidate else 'None',
            )

        # --- Accumulate time on existing candidate ---
        if self._candidate is not None and audio_active:
            self._candidate['segundos_acumulados'] += self.ACCUMULATION_INTERVAL
            self._candidate['last_seen'] = time.time()

            # Update porcentaje en tiempo real para la UI
            segundos = self._candidate['segundos_acumulados']
            duracion_seg = self._candidate['duracion_seg']
            min_time = self._config.min_detection_time
            if duracion_seg > 0:
                self._candidate['porcentaje'] = min((segundos / duracion_seg) * 100.0, 100.0)
            else:
                self._candidate['porcentaje'] = min((segundos / max(min_time, 1)) * 100.0, 100.0)

            # Check if we should save the play
            if not self._candidate.get('play_guardado', False):
                self._try_save_play()

        # --- Fingerprint query ---
        now = time.monotonic()
        should_query = (
            audio_active
            and (now - self._last_query_time) >= self.MIN_QUERY_INTERVAL
        )

        if should_query:
            self._last_query_time = now
            self._do_fingerprint_query()

        # --- Reset if no audio and no candidate ---
        if not audio_active and self._candidate is None:
            self._confirmation_count = 0
            self._last_match_key = None
            self._pending_match = None

    def _do_fingerprint_query(self) -> None:
        from src.fingerprint import FingerprintEngine

        if not FingerprintEngine.is_available():
            logger.warning("ScannerManager: fpcalc not available")
            return

        pcm = self._audio.capture_sample(seconds=self.SAMPLE_SECONDS)
        if pcm is None:
            logger.debug("ScannerManager: buffer not full enough for fingerprint")
            return

        fp_result = FingerprintEngine.generate_raw(pcm, self._audio.SAMPLE_RATE)
        if fp_result is None:
            logger.debug("ScannerManager: fingerprint generation failed")
            return

        values = fp_result.get('values', [])
        if not values:
            return

        match = self._matcher.match(values)
        if match is None:
            logger.debug("ScannerManager: no match found")
            self._confirmation_count = 0
            self._last_match_key = None
            return

        match_key = self._make_match_key(match)
        logger.debug(
            "ScannerManager: match '%s - %s' score=%.3f",
            match.get('artista', ''),
            match.get('titulo', ''),
            match.get('score', 0),
        )

        # Check for consecutive confirmations
        if match_key == self._last_match_key:
            self._confirmation_count += 1
        else:
            self._last_match_key = match_key
            self._confirmation_count = 1
            self._pending_match = match

        if self._confirmation_count >= self.REQUIRED_CONFIRMATIONS:
            if self._candidate is None:
                self._create_candidate(match)
            elif self._make_match_key(self._candidate) != match_key:
                # Different track confirmed - save current, start new
                logger.info("ScannerManager: track changed, resetting candidate")
                self._candidate = None
                self._confirmation_count = 1
                self._create_candidate(match)

    # ------------------------------------------------------------------
    # Candidate management
    # ------------------------------------------------------------------

    def _create_candidate(self, match: dict[str, Any]) -> None:
        audio_detected_at = self._audio.audio_detected_at
        pre_credit = 0.0
        if audio_detected_at > 0:
            pre_credit = min(time.time() - audio_detected_at, self._config.min_detection_time)

        self._candidate = {
            'fuente': 'local_match',
            'artista': match.get('artista', ''),
            'titulo': match.get('titulo', ''),
            'duracion_seg': float(match.get('duration_seg', 0)),
            'isrc': match.get('isrc', ''),
            'isrc_fuente': 'catalog' if match.get('isrc') else '',
            'in_catalog': match.get('in_catalog', True),
            'is_promovida': match.get('is_promovida', False),
            'confianza': float(match.get('score', 0)),
            'first_seen': time.time(),
            'last_seen': time.time(),
            'segundos_acumulados': pre_credit,
            'play_guardado': False,
        }
        logger.info(
            "ScannerManager: candidate created '%s - %s' (pre_credit=%.1fs)",
            match.get('artista', ''),
            match.get('titulo', ''),
            pre_credit,
        )

    def _try_save_play(self) -> None:
        c = self._candidate
        if c is None or c.get('play_guardado', False):
            return

        segundos = c['segundos_acumulados']
        duracion_seg = c['duracion_seg']

        # Porcentaje basado en tiempo (no en confianza)
        min_time = self._config.min_detection_time
        if duracion_seg > 0:
            porcentaje = min((segundos / duracion_seg) * 100.0, 100.0)
        else:
            porcentaje = min((segundos / max(min_time, 1)) * 100.0, 100.0)

        umbral = self._config.umbral_porcentaje

        logger.debug(
            "ScannerManager: _try_save_play '%s' segundos=%.1f duracion=%.1f pct=%.1f umbral=%.1f",
            c['titulo'], segundos, duracion_seg, porcentaje, umbral,
        )

        if segundos >= min_time and porcentaje >= umbral:
            self._save_play(c, segundos, porcentaje)
            c['play_guardado'] = True
            logger.info(
                "ScannerManager: play saved for '%s - %s' (%.1fs, %.1f%%)",
                c['artista'], c['titulo'], segundos, porcentaje,
            )

    def _save_play(self, candidate: dict, segundos: float, porcentaje: float) -> None:
        venue_id = self._config.venue_id
        artista = candidate['artista']
        titulo = candidate['titulo']

        # Hour bucket for idempotency: truncate to the hour
        now_dt = datetime.datetime.utcnow()
        hour_bucket = now_dt.strftime('%Y-%m-%dT%H')
        key_raw = f"{venue_id}|{artista.lower()}|{titulo.lower()}|{hour_bucket}"
        idempotency_key = hashlib.sha256(key_raw.encode('utf-8')).hexdigest()

        duracion_seg = candidate['duracion_seg']
        # Format duration as HH:MM:SS
        total_secs = int(duracion_seg)
        duracion_str = f"{total_secs // 3600:02d}:{(total_secs % 3600) // 60:02d}:{total_secs % 60:02d}"

        timestamp = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        contenido = f"{artista} - {titulo}"

        record = {
            'idempotency_key': idempotency_key,
            'timestamp': timestamp,
            'venue_id': venue_id,
            'fuente': candidate.get('fuente', 'local_match'),
            'contenido': contenido,
            'artista': artista,
            'titulo': titulo,
            'duracion': duracion_str,
            'isrc': candidate.get('isrc', ''),
            'isrc_fuente': candidate.get('isrc_fuente', ''),
            'in_catalog': 1 if candidate.get('in_catalog') else 0,
            'is_promovida': 1 if candidate.get('is_promovida') else 0,
            'porcentaje': porcentaje,
            'segundos_escuchados': segundos,
            'duracion_seg': duracion_seg,
            'confianza': candidate.get('confianza', 0.0),
            'created_at': time.time(),
        }

        self._db.save_play(record)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_match_key(match_or_candidate: dict) -> str:
        artista = match_or_candidate.get('artista', '').lower().strip()
        titulo = match_or_candidate.get('titulo', '').lower().strip()
        return f"{artista}|{titulo}"

    def _notify_status(self, status: str) -> None:
        if self.on_status_change is not None:
            try:
                self.on_status_change(status)
            except Exception as exc:
                logger.error("ScannerManager: on_status_change callback error: %s", exc)
