import logging
import os
import sqlite3
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SumarteRed')
PLAYS_DB_PATH = os.path.join(APPDATA_DIR, 'plays.db')

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plays (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key     TEXT UNIQUE NOT NULL,
    timestamp           TEXT NOT NULL,
    venue_id            TEXT NOT NULL DEFAULT '',
    fuente              TEXT NOT NULL,
    contenido           TEXT NOT NULL,
    artista             TEXT NOT NULL DEFAULT '',
    titulo              TEXT NOT NULL DEFAULT '',
    duracion            TEXT NOT NULL,
    isrc                TEXT NOT NULL DEFAULT '',
    isrc_fuente         TEXT NOT NULL DEFAULT '',
    in_catalog          INTEGER NOT NULL DEFAULT 0,
    is_promovida        INTEGER NOT NULL DEFAULT 0,
    porcentaje          REAL NOT NULL DEFAULT 0,
    segundos_escuchados REAL NOT NULL DEFAULT 0,
    duracion_seg        REAL NOT NULL DEFAULT 0,
    confianza           REAL NOT NULL DEFAULT 0,
    enviado             INTEGER NOT NULL DEFAULT 0,
    intentos            INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL
);
"""


class DatabaseManager:
    def __init__(self, db_path: str = PLAYS_DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(SCHEMA_SQL)
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_play(self, record: dict[str, Any]) -> bool:
        """Insert a play record. Returns True on success."""
        sql = """
        INSERT OR IGNORE INTO plays (
            idempotency_key, timestamp, venue_id, fuente, contenido,
            artista, titulo, duracion, isrc, isrc_fuente,
            in_catalog, is_promovida, porcentaje, segundos_escuchados,
            duracion_seg, confianza, enviado, intentos, created_at
        ) VALUES (
            :idempotency_key, :timestamp, :venue_id, :fuente, :contenido,
            :artista, :titulo, :duracion, :isrc, :isrc_fuente,
            :in_catalog, :is_promovida, :porcentaje, :segundos_escuchados,
            :duracion_seg, :confianza, 0, 0, :created_at
        )
        """
        with self._lock:
            conn = self._connect()
            try:
                record.setdefault('created_at', time.time())
                cursor = conn.execute(sql, record)
                conn.commit()
                return cursor.rowcount > 0
            except Exception as exc:
                logger.error("DatabaseManager.save_play error: %s", exc, exc_info=True)
                return False
            finally:
                conn.close()

    def fetch_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return up to `limit` unsent plays."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM plays
                    WHERE enviado=0 AND intentos < 20
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [dict(row) for row in rows]
            except Exception as exc:
                logger.error("DatabaseManager.fetch_pending error: %s", exc)
                return []
            finally:
                conn.close()

    def mark_sent(self, play_id: int) -> None:
        """Mark a play as successfully sent."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE plays SET enviado=1 WHERE id=?",
                    (play_id,),
                )
                conn.commit()
            except Exception as exc:
                logger.error("DatabaseManager.mark_sent error: %s", exc)
            finally:
                conn.close()

    def increment_attempts(self, play_id: int) -> None:
        """Increment the retry counter for a play."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE plays SET intentos=intentos+1 WHERE id=?",
                    (play_id,),
                )
                conn.commit()
            except Exception as exc:
                logger.error("DatabaseManager.increment_attempts error: %s", exc)
            finally:
                conn.close()

    def count_pending(self) -> int:
        """Return count of unsent plays."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM plays WHERE enviado=0 AND intentos < 20"
                ).fetchone()
                return row[0] if row else 0
            except Exception as exc:
                logger.error("DatabaseManager.count_pending error: %s", exc)
                return 0
            finally:
                conn.close()
