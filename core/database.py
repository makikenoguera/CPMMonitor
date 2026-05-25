"""
CPM Tracks - Gestor de base de datos local (SQLite)
Maneja la cola offline y el historial de reproducciones.
"""
import sqlite3
import os
import time
import hashlib

DATA_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "CPMTracks")
DB_PATH  = os.path.join(DATA_DIR, "cpm_tracks.db")


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = _connect()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS plays (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT UNIQUE NOT NULL,
            timestamp      TEXT NOT NULL,
            id_local       TEXT NOT NULL,
            fuente         TEXT NOT NULL,
            contenido      TEXT NOT NULL,
            duracion       TEXT NOT NULL,
            isrc           TEXT NOT NULL,
            enviado        INTEGER NOT NULL DEFAULT 0,
            intentos       INTEGER NOT NULL DEFAULT 0,
            created_at     REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enviado ON plays(enviado);
    """)
    con.commit()
    con.close()


def _connect():
    return sqlite3.connect(DB_PATH, timeout=5)


def _make_key(id_local, fuente, contenido, timestamp):
    raw = f"{id_local}|{fuente}|{contenido}|{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def guardar_play(id_local, fuente, contenido, duracion, isrc, timestamp=None, porcentaje=0, segundos_escuchados=0, duracion_seg=0):
    """Guarda una reproducción en la cola local. Retorna True si es nueva."""
    if timestamp is None:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    key = _make_key(id_local, fuente, contenido, timestamp)
    try:
        con = _connect()
        con.execute(
            """INSERT OR IGNORE INTO plays
               (idempotency_key, timestamp, id_local, fuente, contenido, duracion, isrc, porcentaje, segundos_escuchados, duracion_seg, enviado, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,0,?)""",
            (key, timestamp, id_local, fuente, contenido, duracion, isrc, porcentaje, segundos_escuchados, duracion_seg, time.time())
        )
        insertado = con.total_changes > 0
        con.commit()
        con.close()
        return insertado
    except Exception as e:
        print(f"[DB] Error guardando play: {e}")
        return False


def obtener_pendientes(limite=100):
    """Retorna registros no enviados o con menos de 5 intentos."""
    try:
        con = _connect()
        rows = con.execute(
            """SELECT id, idempotency_key, timestamp, id_local, fuente,
                      contenido, duracion, isrc, intentos
               FROM plays
               WHERE enviado = 0 AND intentos < 5
               ORDER BY created_at ASC
               LIMIT ?""",
            (limite,)
        ).fetchall()
        con.close()
        return rows
    except Exception as e:
        print(f"[DB] Error obteniendo pendientes: {e}")
        return []


def marcar_enviado(record_id):
    try:
        con = _connect()
        con.execute("UPDATE plays SET enviado=1 WHERE id=?", (record_id,))
        con.commit()
        con.close()
    except Exception as e:
        print(f"[DB] Error marcando enviado: {e}")


def incrementar_intentos(record_id):
    try:
        con = _connect()
        con.execute("UPDATE plays SET intentos=intentos+1 WHERE id=?", (record_id,))
        con.commit()
        con.close()
    except Exception as e:
        print(f"[DB] Error incrementando intentos: {e}")


def contar_pendientes():
    try:
        con = _connect()
        n = con.execute("SELECT COUNT(*) FROM plays WHERE enviado=0").fetchone()[0]
        con.close()
        return n
    except:
        return 0


def historial_reciente(limite=50):
    try:
        con = _connect()
        rows = con.execute(
            """SELECT timestamp, fuente, contenido, duracion, isrc, enviado
               FROM plays ORDER BY created_at DESC LIMIT ?""",
            (limite,)
        ).fetchall()
        con.close()
        return rows
    except:
        return []
