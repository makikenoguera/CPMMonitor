import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

SYNC_INTERVAL = 30.0   # seconds
MAX_ATTEMPTS = 20


class SyncManager:
    """Background thread that periodically syncs pending plays to the server."""

    def __init__(self, config, db) -> None:
        self._config = config
        self._db = db
        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._timer: Optional[threading.Timer] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._schedule_next()
        logger.info("SyncManager: started (interval=%ss)", SYNC_INTERVAL)

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("SyncManager: stopped")

    def sync_now(self) -> None:
        """Trigger an immediate sync (runs in current thread)."""
        self._do_sync()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _schedule_next(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(SYNC_INTERVAL, self._on_timer)
        self._timer.daemon = True
        self._timer.start()

    def _on_timer(self) -> None:
        if not self._running:
            return
        try:
            self._do_sync()
        except Exception as exc:
            logger.error("SyncManager._do_sync error: %s", exc, exc_info=True)
        finally:
            self._schedule_next()

    def _do_sync(self) -> None:
        if not self._config.is_activated:
            return

        pending = self._db.fetch_pending(limit=50)
        if not pending:
            return

        logger.info("SyncManager: syncing %d pending plays", len(pending))

        from src.api_client import APIClient
        client = APIClient(self._config)

        # Build API payload list
        payload_plays = [self._record_to_api_play(p) for p in pending]

        success = client.send_plays(payload_plays)

        if success:
            for play in pending:
                self._db.mark_sent(play['id'])
            logger.info("SyncManager: successfully sent %d plays", len(pending))
        else:
            for play in pending:
                self._db.increment_attempts(play['id'])
            logger.warning("SyncManager: failed to send plays, incremented attempt counters")

    @staticmethod
    def _record_to_api_play(record: dict[str, Any]) -> dict[str, Any]:
        """Map database row dict to API payload dict."""
        return {
            'idempotency_key': record.get('idempotency_key', ''),
            'timestamp': record.get('timestamp', ''),
            'venue_id': record.get('venue_id', ''),
            'fuente': record.get('fuente', ''),
            'contenido': record.get('contenido', ''),
            'artista': record.get('artista', ''),
            'titulo': record.get('titulo', ''),
            'duracion': record.get('duracion', ''),
            'isrc': record.get('isrc', ''),
            'isrc_fuente': record.get('isrc_fuente', ''),
            'in_catalog': bool(record.get('in_catalog', 0)),
            'is_promovida': bool(record.get('is_promovida', 0)),
            'porcentaje': float(record.get('porcentaje', 0)),
            'segundos_escuchados': float(record.get('segundos_escuchados', 0)),
            'duracion_seg': float(record.get('duracion_seg', 0)),
            'confianza': float(record.get('confianza', 0)),
        }
