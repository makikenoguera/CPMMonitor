import os
import sqlite3
import struct
import threading
from typing import Any

APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SumarteRed')
CATALOG_DB_PATH = os.path.join(APPDATA_DIR, 'catalog.db')

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY,
    artista      TEXT    NOT NULL DEFAULT '',
    titulo       TEXT    NOT NULL DEFAULT '',
    isrc         TEXT    NOT NULL DEFAULT '',
    duration_seg REAL    NOT NULL DEFAULT 0,
    fp_raw       BLOB    NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    updated_at   INTEGER NOT NULL DEFAULT 0,
    is_promovida INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
INSERT OR IGNORE INTO meta(key,value) VALUES ('version','0');
INSERT OR IGNORE INTO meta(key,value) VALUES ('last_sync','0');
"""


def _encode_fp(fp: list[int]) -> bytes:
    """Encode a list of int32 values to little-endian BLOB."""
    return struct.pack('<' + 'i' * len(fp), *fp)


def _decode_fp(blob: bytes) -> list[int]:
    """Decode a little-endian int32 BLOB to a list of ints."""
    count = len(blob) // 4
    return list(struct.unpack('<' + 'i' * count, blob))


class CatalogStore:
    def __init__(self, db_path: str = CATALOG_DB_PATH):
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

    def _get_meta(self, key: str) -> str:
        conn = self._connect()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row[0] if row else '0'
        finally:
            conn.close()

    def _set_meta(self, key: str, value: str) -> None:
        conn = self._connect()
        try:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", (key, value))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def local_version(self) -> int:
        with self._lock:
            return int(self._get_meta('version'))

    @local_version.setter
    def local_version(self, value: int) -> None:
        with self._lock:
            self._set_meta('version', str(value))

    @property
    def last_sync(self) -> int:
        with self._lock:
            return int(self._get_meta('last_sync'))

    @last_sync.setter
    def last_sync(self, value: int) -> None:
        with self._lock:
            self._set_meta('last_sync', str(value))

    @property
    def track_count(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) FROM tracks WHERE active=1").fetchone()
                return row[0] if row else 0
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_batch(self, tracks: list[dict[str, Any]]) -> None:
        """Insert or replace a batch of track records.

        Each dict must have keys:
            id, artista, titulo, isrc, duration_seg,
            fp_raw (bytes), active, updated_at, is_promovida
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO tracks
                        (id, artista, titulo, isrc, duration_seg, fp_raw, active, updated_at, is_promovida)
                    VALUES
                        (:id, :artista, :titulo, :isrc, :duration_seg, :fp_raw, :active, :updated_at, :is_promovida)
                    """,
                    tracks,
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_all(self) -> list[dict[str, Any]]:
        """Return all active tracks with fp decoded to list[int]."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT id, artista, titulo, isrc, duration_seg,
                           fp_raw, active, updated_at, is_promovida
                    FROM tracks
                    WHERE active=1
                    """
                ).fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    blob = d.pop('fp_raw')
                    d['fp'] = _decode_fp(blob) if blob else []
                    result.append(d)
                return result
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Helpers for catalog_manager
    # ------------------------------------------------------------------

    @staticmethod
    def encode_fp(fp: list[int]) -> bytes:
        return _encode_fp(fp)
