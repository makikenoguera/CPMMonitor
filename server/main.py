"""
SumarteRed Monitor Server v3.0
FastAPI backend para el sistema de monitoreo de música.

Endpoints:
  GET  /v1/venue/:venue_id   — verifica que venue_id + API key sean válidos
  POST /v1/identify          — identifica fingerprint y valida contra catálogo
  POST /v1/plays             — recibe plays en lote desde la app

Auth: X-API-Key: <venue_api_key>

Setup:
  pip install fastapi uvicorn aiohttp aiofiles
  python main.py

  Para producción: gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
"""

import os
import re
import json
import sqlite3
import hashlib
import asyncio
import logging
import base64
import struct
import ctypes
import shutil
import tempfile
import subprocess
import unicodedata
from typing import Optional
from datetime import datetime, timezone

import ssl
import certifi
import aiohttp
import numpy as np

# ── Chromaprint via ctypes (sin dependencias Python) ─────────────────────────
# libchromaprint.dylib está en /usr/local/lib (Homebrew Intel) pero Python
# no lo busca ahí. Cargamos con ruta absoluta y exponemos decode_fingerprint.
def _load_libchromaprint():
    candidates = [
        'libchromaprint.dylib',
        '/usr/local/lib/libchromaprint.dylib',        # Homebrew Intel (x86_64)
        '/opt/homebrew/lib/libchromaprint.dylib',     # Homebrew ARM (M1/M2)
        'libchromaprint.so.1',                        # Linux
    ]
    for path in candidates:
        try:
            lib = ctypes.cdll.LoadLibrary(path)
            lib.chromaprint_decode_fingerprint.restype = ctypes.c_int
            lib.chromaprint_decode_fingerprint.argtypes = [
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_int,
            ]
            lib.chromaprint_dealloc.restype = None
            lib.chromaprint_dealloc.argtypes = [ctypes.c_void_p]
            return lib
        except Exception:
            pass
    return None

_libchromaprint = _load_libchromaprint()
_CHROMAPRINT_OK = _libchromaprint is not None
from fastapi import FastAPI, HTTPException, Header, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sumartered")

app = FastAPI(title="SumarteRed Monitor", version="3.0.0")


@app.on_event("startup")
async def startup():
    """Inicializa las bases de datos al arrancar (funciona con uvicorn directo o gunicorn)."""
    init_plays_db()
    init_venues_db()
    init_compat_db()   # tablas para la capa de compatibilidad del dashboard
    load_fp_index()              # carga fingerprints en memoria para matching local
    load_fp_index_promovidas()   # sub-índice prioritario: solo canciones promovidas


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuración ──────────────────────────────────────────────────────────────
ACOUSTID_API_KEY = os.getenv("ACOUSTID_API_KEY", "")   # API key del servidor para AcousticID

# Ruta absoluta al catálogo: permite arrancar el servidor desde cualquier directorio
_SERVER_DIR      = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_FP_DB   = os.path.join(_SERVER_DIR, "..", "FingerprintBuilder", "fingerprints.db")
FINGERPRINTS_DB  = os.getenv("FINGERPRINTS_DB", _DEFAULT_FP_DB)

PLAYS_DB         = os.getenv("PLAYS_DB",  os.path.join(_SERVER_DIR, "plays.db"))
VENUES_DB        = os.getenv("VENUES_DB", os.path.join(_SERVER_DIR, "venues.db"))
SCORE_THRESHOLD  = float(os.getenv("SCORE_THRESHOLD", "0.80"))

# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_plays_db():
    with get_conn(PLAYS_DB) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS plays (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key     TEXT UNIQUE NOT NULL,
            timestamp           TEXT NOT NULL,
            venue_id            TEXT NOT NULL,
            fuente              TEXT NOT NULL DEFAULT 'acr',
            contenido           TEXT NOT NULL DEFAULT '',
            artista             TEXT NOT NULL DEFAULT '',
            titulo              TEXT NOT NULL DEFAULT '',
            duracion            TEXT NOT NULL DEFAULT '',
            isrc                TEXT NOT NULL DEFAULT '',
            isrc_fuente         TEXT NOT NULL DEFAULT '',
            in_catalog          INTEGER NOT NULL DEFAULT 0,
            porcentaje          REAL NOT NULL DEFAULT 0,
            segundos_escuchados REAL NOT NULL DEFAULT 0,
            duracion_seg        REAL NOT NULL DEFAULT 0,
            confianza           REAL NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            promovida_id        TEXT DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_plays_venue_id    ON plays(venue_id);
        CREATE INDEX IF NOT EXISTS idx_plays_created_at  ON plays(created_at);
        CREATE INDEX IF NOT EXISTS idx_plays_isrc        ON plays(isrc);

        CREATE TABLE IF NOT EXISTS artistas (
            id          TEXT PRIMARY KEY,
            nombre      TEXT NOT NULL,
            email       TEXT DEFAULT '',
            telefono    TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS canciones_promovidas (
            id               TEXT PRIMARY KEY,
            artista_id       TEXT REFERENCES artistas(id),
            artista_nombre   TEXT NOT NULL DEFAULT '',
            titulo           TEXT NOT NULL,
            isrc             TEXT DEFAULT '',
            genero           TEXT DEFAULT '',
            link_spotify     TEXT DEFAULT '',
            link_youtube     TEXT DEFAULT '',
            links_otros      TEXT DEFAULT '',
            fecha_inicio     TEXT DEFAULT '',
            fecha_fin        TEXT DEFAULT '',
            creditos_total   INTEGER DEFAULT 0,
            creditos_usados  INTEGER DEFAULT 0,
            tarifa_venue     REAL DEFAULT 500,
            activa           INTEGER DEFAULT 1,
            created_at       TEXT DEFAULT (datetime('now'))
        );
        """)
        log.info(f"[DB] plays.db lista en {PLAYS_DB}")


def init_venues_db():
    """Crea la tabla de venues con datos de ejemplo si no existe."""
    with get_conn(VENUES_DB) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS venues (
            id           TEXT PRIMARY KEY,
            nombre       TEXT NOT NULL,
            ciudad       TEXT NOT NULL DEFAULT '',
            api_key      TEXT UNIQUE NOT NULL,
            activo       INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        # Venue de ejemplo para desarrollo local
        conn.execute("""
            INSERT OR IGNORE INTO venues (id, nombre, ciudad, api_key)
            VALUES ('VENUE-001', 'SumarteRed Demo', 'Bogotá', 'demo-key-sumartered-2024')
        """)
        log.info(f"[DB] venues.db lista en {VENUES_DB}")


def init_compat_db():
    """Crea tablas para la capa de compatibilidad del dashboard (auth, catálogo, planes, etc.)."""
    with get_conn(PLAYS_DB) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'cpm_interno',
            password_hash TEXT NOT NULL,
            id_local TEXT DEFAULT '',
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sesiones (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS planes_promo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            color TEXT DEFAULT '#3D8EFF',
            precio_plan REAL DEFAULT 0,
            precio_play REAL DEFAULT 500,
            total_plays INTEGER DEFAULT 100,
            dias_semana TEXT DEFAULT '[]',
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS catalogo_cpm (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artista TEXT NOT NULL DEFAULT '',
            titulo TEXT NOT NULL DEFAULT '',
            isrc TEXT DEFAULT '',
            genero TEXT DEFAULT '',
            pvp REAL DEFAULT 3000,
            valor_establecimiento REAL DEFAULT 500,
            spotify_url TEXT DEFAULT '',
            youtube_url TEXT DEFAULT '',
            cdn_url TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL DEFAULT '',
            imagen_url TEXT DEFAULT '',
            boton_texto TEXT DEFAULT '',
            boton_url TEXT DEFAULT '',
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)

        # Tabla de configuración global del sistema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Valores por defecto de configuración si no existen
        defaults = [("precio_por_play", "4000"), ("pct_estab", "12.5"), ("umbral_pct", "80")]
        for k, v in defaults:
            conn.execute("INSERT OR IGNORE INTO system_config (key, value) VALUES (?,?)", (k, v))

        # Migraciones: agregar columnas nuevas a canciones_promovidas si no existen
        for col, defn in [("plan_id", "INTEGER DEFAULT NULL"), ("dias_semana", "TEXT DEFAULT '[]'")]:
            try:
                conn.execute(f"ALTER TABLE canciones_promovidas ADD COLUMN {col} {defn}")
            except Exception:
                pass  # La columna ya existe

        # Migración: promovida_id en plays (identifica qué plays son de promovidas)
        try:
            conn.execute("ALTER TABLE plays ADD COLUMN promovida_id TEXT DEFAULT NULL")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_plays_promovida ON plays(promovida_id)")
            log.info("[Migración] Columna promovida_id añadida a plays")
        except Exception:
            pass  # Ya existe

        # Usuario admin por defecto (solo si no hay usuarios)
        if conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
            import uuid as _uuid
            uid = str(_uuid.uuid4())
            pwd_hash = hashlib.sha256("SumarteRed2025".encode()).hexdigest()
            conn.execute(
                "INSERT INTO usuarios (id, email, nombre, rol, password_hash) VALUES (?,?,?,?,?)",
                (uid, "admin@sumartered.com", "Administrador", "superadmin", pwd_hash)
            )
            log.info("[Compat] Usuario admin creado: admin@sumartered.com / SumarteRed2025")

        # Planes por defecto (solo si no hay planes)
        if conn.execute("SELECT COUNT(*) FROM planes_promo").fetchone()[0] == 0:
            default_plans = [
                ("Bronce", "#CD7F32", 50000,  500,  100, json.dumps([0,1,2,3,4,5,6])),
                ("Plata",  "#A0A0A8", 100000, 1000, 100, json.dumps([0,1,2,3,4,5,6])),
                ("Oro",    "#FFD700", 200000, 2000, 100, json.dumps([0,1,2,3,4,5,6])),
            ]
            conn.executemany(
                "INSERT INTO planes_promo (nombre, color, precio_plan, precio_play, total_plays, dias_semana) VALUES (?,?,?,?,?,?)",
                default_plans
            )
            log.info("[Compat] Planes por defecto creados (Bronce/Plata/Oro)")

    log.info("[Compat] Tablas de compatibilidad listas")


def verify_api_key(venue_id: str, api_key: str) -> Optional[dict]:
    """Devuelve el venue si venue_id + api_key son válidos, None si no."""
    try:
        with get_conn(VENUES_DB) as conn:
            row = conn.execute(
                "SELECT id, nombre, ciudad FROM venues WHERE id=? AND api_key=? AND activo=1",
                (venue_id, api_key)
            ).fetchone()
            if not row:
                log.warning(f"[Auth] FAIL venue_id={repr(venue_id)} api_key=...{repr(api_key[-6:]) if len(api_key) >= 6 else '(empty)'}")
            return dict(row) if row else None
    except Exception as e:
        log.error(f"[Auth] Error verificando API key: {e}")
        return None


# ── Índice local de fingerprints ───────────────────────────────────────────────
# Se carga en memoria al arrancar. Cada entrada es:
#   {"artista", "titulo", "isrc", "duration", "fp": np.ndarray int32}

_fp_index: list = []
_fp_index_promovidas: list = []  # sub-índice prioritario: solo canciones promovidas


def _decode_chromaprint(fp_str: str) -> Optional[np.ndarray]:
    """
    Decodifica un fingerprint Chromaprint → numpy array int32.

    Formato A) Base64url comprimido (fpcalc sin -raw) → libchromaprint via ctypes
    Formato B) Enteros separados por coma (fpcalc -raw) → parseados directamente

    NOTA: El "fallback" de tratar los bytes comprimidos como int32 es INCORRECTO
    (produce valores de ruido) y fue eliminado. Sin libchromaprint, solo funciona
    el formato B (raw).
    """
    if not fp_str:
        return None

    # Formato B: enteros separados por coma (fpcalc -raw)
    if "," in fp_str:
        try:
            vals = [int(v.strip()) for v in fp_str.split(",") if v.strip()]
            if len(vals) >= 10:
                return np.array(vals, dtype=np.uint32).view(np.int32)
        except Exception as e:
            log.warning(f"[FP] fallo parseando raw-int32: {e!r}")
        return None

    # Formato A: base64url comprimido con Golomb-Rice → decode via libchromaprint
    if _CHROMAPRINT_OK:
        try:
            fp_bytes = fp_str.encode('ascii') if isinstance(fp_str, str) else fp_str
            fp_ptr   = ctypes.POINTER(ctypes.c_int32)()
            fp_size  = ctypes.c_int(0)
            algorithm = ctypes.c_int(0)

            ret = _libchromaprint.chromaprint_decode_fingerprint(
                fp_bytes, len(fp_bytes),
                ctypes.byref(fp_ptr),
                ctypes.byref(fp_size),
                ctypes.byref(algorithm),
                1,  # base64=1
            )
            if ret == 1 and fp_size.value >= 10:
                arr = np.ctypeslib.as_array(fp_ptr, shape=(fp_size.value,)).copy()
                _libchromaprint.chromaprint_dealloc(fp_ptr)
                return arr
        except Exception as e:
            log.warning(f"[FP] ctypes decode failed: {e!r}")

    log.debug("[FP] libchromaprint no disponible y fingerprint no es formato raw")
    return None


def _sliding_score(query: np.ndarray, ref: np.ndarray) -> float:
    """
    Busca la mejor alineación de `query` dentro de `ref` mediante ventana deslizante.
    Retorna similaridad 0-1 (1 = idéntico).

    Para clips cortos (10s ≈ 59 valores frente a canción completa ≈ 900+):
    - step pequeño = más posiciones revisadas = mejor alineación
    - step = qlen//3 sólo revisaba ~3 posiciones → fácil perder el encaje real
    """
    qlen = len(query)
    rlen = len(ref)
    if qlen == 0 or rlen == 0:
        return 0.0

    best  = 0.0
    # Paso fino: revisar cada posición si el fingerprint es corto (<120 valores),
    # o cada qlen//8 posiciones si es largo. Compromiso velocidad/exhaustividad.
    step  = 1 if qlen < 120 else max(1, qlen // 8)
    limit = max(1, rlen - qlen + 1)

    for offset in range(0, limit, step):
        window = ref[offset : offset + qlen]
        wlen   = len(window)
        if wlen < max(10, qlen // 2):
            break
        xor        = (query[:wlen] ^ window).view(np.uint8)
        diff_bits  = int(np.unpackbits(xor).sum())
        total_bits = wlen * 32
        score      = 1.0 - diff_bits / total_bits
        if score > best:
            best = score
            if best > 0.92:           # excelente → salir temprano
                break

    return best


def _ensure_active_column():
    """Agrega columna `active` a tracks si no existe (migración one-time)."""
    if not os.path.exists(FINGERPRINTS_DB):
        return
    try:
        with get_conn(FINGERPRINTS_DB) as conn:
            conn.execute("ALTER TABLE tracks ADD COLUMN active INTEGER DEFAULT 1")
            conn.execute("UPDATE tracks SET active=1 WHERE active IS NULL")
    except Exception:
        pass  # La columna ya existe


def load_fp_index():
    """
    Carga todos los fingerprints procesados de fingerprints.db en memoria.
    Precalcula fp_raw_b64 (raw int32 LE bytes en base64) para servir al cliente
    sin tener que re-decodificar en cada request del catálogo.
    """
    global _fp_index
    if not os.path.exists(FINGERPRINTS_DB):
        log.warning("[FP Index] fingerprints.db no encontrada — búsqueda local deshabilitada")
        return

    _ensure_active_column()

    try:
        with get_conn(FINGERPRINTS_DB) as conn:
            rows = conn.execute(
                """SELECT id, artista_final, titulo_final, isrc, duration_seg,
                          fingerprint, active, updated_at
                   FROM tracks
                   WHERE procesado = 1 AND fingerprint IS NOT NULL
                     AND (active IS NULL OR active = 1)"""
            ).fetchall()

        index = []
        skipped = 0
        for row in rows:
            arr = _decode_chromaprint(row["fingerprint"])
            if arr is None or len(arr) < 20:
                skipped += 1
                continue
            # raw bytes little-endian int32 → base64 para servir al cliente Swift
            fp_raw_b64 = base64.b64encode(arr.astype('<i4').tobytes()).decode('ascii')
            # unix timestamp de updated_at (puede ser float, int, o string ISO)
            ut = row["updated_at"]
            try:
                updated_ts = int(float(ut)) if ut else 0
            except (ValueError, TypeError):
                try:
                    updated_ts = int(datetime.strptime(str(ut)[:19], "%Y-%m-%d %H:%M:%S")
                                     .replace(tzinfo=timezone.utc).timestamp())
                except Exception:
                    updated_ts = 0
            index.append({
                "id":         row["id"],
                "artista":    row["artista_final"] or "",
                "titulo":     row["titulo_final"]  or "",
                "isrc":       row["isrc"]          or "",
                "duration":   row["duration_seg"]  or 0,
                "fp":         arr,
                "fp_raw_b64": fp_raw_b64,
                "active":     bool(row["active"] if row["active"] is not None else 1),
                "updated_ts": updated_ts,
            })

        _fp_index = index
        log.info(f"[FP Index] {len(index)} tracks cargados ({skipped} omitidos)")
    except Exception as e:
        log.error(f"[FP Index] Error cargando índice: {e}")


def load_fp_index_promovidas():
    """
    Construye el sub-índice prioritario de fingerprints para canciones promovidas.
    Se llama después de load_fp_index(). Cruza canciones_promovidas (plays.db)
    contra _fp_index (fingerprints.db) por ISRC exacto o artista+titulo normalizado.
    """
    global _fp_index_promovidas
    if not _fp_index or not os.path.exists(PLAYS_DB):
        _fp_index_promovidas = []
        return

    def _norm(s: str) -> str:
        import unicodedata as _ud
        t = (s or "").strip().lower()
        t = _ud.normalize("NFKD", t)
        return "".join(c for c in t if not _ud.combining(c))

    try:
        with get_conn(PLAYS_DB) as conn:
            promos = conn.execute(
                "SELECT isrc, artista_nombre, titulo FROM canciones_promovidas"
            ).fetchall()

        promo_isrcs  = {row["isrc"].strip().upper() for row in promos if row["isrc"]}
        promo_titles = {
            (_norm(row["artista_nombre"]), _norm(row["titulo"]))
            for row in promos
        }

        matched = []
        for entry in _fp_index:
            isrc_match  = bool(entry["isrc"]) and entry["isrc"].strip().upper() in promo_isrcs
            title_match = (_norm(entry["artista"]), _norm(entry["titulo"])) in promo_titles
            if isrc_match or title_match:
                matched.append(entry)

        _fp_index_promovidas = matched
        log.info(
            f"[FP Promovidas] {len(matched)} fingerprints de canciones promovidas "
            f"(de {len(_fp_index)} totales)"
        )
    except Exception as e:
        log.error(f"[FP Promovidas] Error construyendo índice: {e}")
        _fp_index_promovidas = []


def _search_in_index(query_arr: np.ndarray, index: list, threshold: float) -> Optional[dict]:
    """Busca query_arr en `index`; retorna el mejor match si supera threshold."""
    best_score = 0.0
    best_track = None
    for entry in index:
        score = _sliding_score(query_arr, entry["fp"])
        if score > best_score:
            best_score = score
            best_track = entry
            if best_score > 0.90:
                break
    if best_score >= threshold and best_track:
        return {**best_track, "confianza": best_score}
    return None


def search_by_fingerprint(query_fp: str, threshold: float = 0.70) -> Optional[dict]:
    """
    Busca en el índice local de fingerprints con prioridad para canciones promovidas.

    Fase 1 — busca en _fp_index_promovidas (canciones actualmente promovidas).
              Si hay match, lo retorna de inmediato con is_promovida=True.
    Fase 2 — busca en _fp_index completo (catálogo general).

    Threshold 0.70: empírico para Chromaprint de 10s vs canción completa.
    - <0.50  → azar
    - 0.70   → mínimo confiable para clips cortos
    - >0.85  → match casi seguro
    """
    if not _fp_index:
        return None

    query_arr = _decode_chromaprint(query_fp)
    if query_arr is None or len(query_arr) < 10:
        return None

    # Fase 1: promovidas primero
    if _fp_index_promovidas:
        result = _search_in_index(query_arr, _fp_index_promovidas, threshold)
        if result:
            log.info(
                f"[LocalMatch] ⭐ Promovida: {result['artista']} - {result['titulo']} "
                f"(score={result['confianza']:.2f})"
            )
            return {**result, "is_promovida": True}

    # Fase 2: catálogo completo
    result = _search_in_index(query_arr, _fp_index, threshold)
    if result:
        log.info(
            f"[LocalMatch] ✅ {result['artista']} - {result['titulo']} "
            f"(score={result['confianza']:.2f})"
        )
        return result

    log.info(f"[LocalMatch] Sin match local")
    return None


def search_catalog(artista: str, titulo: str) -> Optional[dict]:
    """
    Busca artista + titulo en el catálogo SumarteRed (fingerprints.db).
    Devuelve el track con su ISRC real si existe.
    """
    if not os.path.exists(FINGERPRINTS_DB):
        return None
    try:
        with get_conn(FINGERPRINTS_DB) as conn:
            # Búsqueda flexible: normaliza mayúsculas y permite coincidencia parcial
            row = conn.execute("""
                SELECT artista_final, titulo_final, isrc, isrc_fuente, acoustid_score
                FROM tracks
                WHERE LOWER(artista_final) = LOWER(?)
                  AND LOWER(titulo_final)  = LOWER(?)
                  AND isrc_estado = 'verificado'
                LIMIT 1
            """, (artista.strip(), titulo.strip())).fetchone()

            if not row:
                # Intento 2: solo titulo (variaciones de nombre de artista)
                row = conn.execute("""
                    SELECT artista_final, titulo_final, isrc, isrc_fuente, acoustid_score
                    FROM tracks
                    WHERE LOWER(titulo_final) = LOWER(?)
                      AND isrc_estado IN ('verificado', 'encontrado')
                    LIMIT 1
                """, (titulo.strip(),)).fetchone()

            return dict(row) if row else None
    except Exception as e:
        log.error(f"[Catalog] Error buscando en catálogo: {e}")
        return None


# ── AcousticID ─────────────────────────────────────────────────────────────────

async def acoustid_lookup(fingerprint: str, duration: int) -> Optional[dict]:
    """
    Consulta la API de AcousticID con el fingerprint del cliente.
    Pide recordings+isrcs para obtener ISRCs reales.
    """
    if not ACOUSTID_API_KEY:
        log.warning("[AcousticID] ACOUSTID_API_KEY no configurada en el servidor")
        return None

    params = {
        "client":      ACOUSTID_API_KEY,
        "meta":        "recordings+isrcs",
        "fingerprint": fingerprint,
        "duration":    str(duration),
    }

    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                "https://api.acoustid.org/v2/lookup",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
    except asyncio.TimeoutError:
        log.warning("[AcousticID] Timeout")
        return None
    except Exception as e:
        log.error(f"[AcousticID] Error: {e}")
        return None

    if data.get("status") != "ok":
        return None

    results = data.get("results", [])
    if not results:
        return None

    best = max(results, key=lambda r: r.get("score", 0))
    score = best.get("score", 0)

    if score < SCORE_THRESHOLD:
        log.info(f"[AcousticID] Score {score:.2f} < threshold {SCORE_THRESHOLD}")
        return None

    recordings = best.get("recordings", [])
    if not recordings:
        return None

    rec = recordings[0]
    artists = rec.get("artists", [])
    artista = artists[0].get("name", "") if artists else ""
    titulo  = rec.get("title", "")

    # Extraer ISRC real de la respuesta
    isrc = ""
    isrcs = rec.get("isrcs", [])
    if isrcs:
        isrc = isrcs[0]  # Primer ISRC disponible

    return {
        "artista":    artista,
        "titulo":     titulo,
        "duracion":   rec.get("duration", duration),
        "isrc":       isrc,
        "isrc_fuente": "acoustid" if isrc else "",
        "confianza":  score,
        "recording_id": rec.get("id", ""),
    }


# ── Modelos Pydantic ───────────────────────────────────────────────────────────

class IdentifyRequest(BaseModel):
    fingerprint: str
    duration:    int
    venue_id:    str


class APIPlay(BaseModel):
    idempotency_key:    str
    timestamp:          str
    venue_id:           str
    fuente:             str = "acr"
    contenido:          str = ""
    artista:            str = ""
    titulo:             str = ""
    duracion:           str = ""
    isrc:               str = ""
    isrc_fuente:        str = ""
    in_catalog:         bool = False
    porcentaje:         float = 0
    segundos_escuchados: float = 0
    duracion_seg:       float = 0
    confianza:          float = 0


class PlaysPayload(BaseModel):
    plays: list[APIPlay]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "SumarteRed Monitor API",
        "version": "3.0.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}


@app.get("/v1/venue/{venue_id}")
async def get_venue(venue_id: str, x_api_key: str = Header(alias="X-API-Key", default="")):
    """Verifica que venue_id + api_key sean válidos. Usado en el setup de la app."""
    venue = verify_api_key(venue_id, x_api_key)
    if not venue:
        raise HTTPException(status_code=401, detail="API key inválida o venue no encontrado")
    return {"ok": True, "nombre_local": venue["nombre"], "ciudad": venue["ciudad"]}


@app.post("/v1/identify")
async def identify(payload: IdentifyRequest, x_api_key: str = Header(alias="X-API-Key", default="")):
    """
    Identifica un fingerprint y valida contra el catálogo SumarteRed.

    Flujo:
    1. Validar API key del venue
    2. Consultar AcousticID con el fingerprint
    3. Cross-check contra catálogo SumarteRed → ISRC real + in_catalog flag
    4. Devolver resultado
    """
    # Autenticación
    venue = verify_api_key(payload.venue_id, x_api_key)
    if not venue:
        raise HTTPException(status_code=401, detail="API key inválida")

    log.info(f"[Identify] venue={payload.venue_id} duration={payload.duration}s")

    # ── 1. Buscar primero en catálogo local por fingerprint ──────────────────
    local = search_by_fingerprint(payload.fingerprint)
    if local:
        isrc        = local.get("isrc") or ""
        isrc_fuente = "sumartered" if isrc else ""
        return {
            "matched":     True,
            "artista":     local["artista"],
            "titulo":      local["titulo"],
            "duracion":    int(local.get("duration") or 0),
            "isrc":        isrc,
            "isrc_fuente": isrc_fuente,
            "in_catalog":  True,
            "confianza":   round(local["confianza"], 3),
        }

    # ── 2. Fallback: AcousticID ──────────────────────────────────────────────
    result = await acoustid_lookup(payload.fingerprint, payload.duration)

    if not result:
        return {"matched": False}

    artista = result["artista"]
    titulo  = result["titulo"]

    # Cross-check contra catálogo SumarteRed para enriquecer ISRC
    catalog_track = search_catalog(artista, titulo)
    in_catalog    = catalog_track is not None
    isrc          = result["isrc"]
    isrc_fuente   = result["isrc_fuente"]

    if catalog_track and catalog_track.get("isrc"):
        isrc        = catalog_track["isrc"]
        isrc_fuente = "sumartered"

    log.info(
        f"[AcousticID] {'✅' if in_catalog else '⚠️ '} {artista} - {titulo} "
        f"(score={result['confianza']:.2f}, ISRC={isrc or '—'}, catálogo={in_catalog})"
    )

    return {
        "matched":     True,
        "artista":     artista,
        "titulo":      titulo,
        "duracion":    result["duracion"],
        "isrc":        isrc,
        "isrc_fuente": isrc_fuente,
        "in_catalog":  in_catalog,
        "confianza":   result["confianza"],
    }


def _normalize_title(title: str) -> str:
    """Normaliza título para matching: quita número de pista, minúsculas, sin acentos."""
    t = title.strip()
    # Quitar número de pista al inicio: "16 Título", "01. Título", "Track 3 - Título"
    t = re.sub(r'^(?:track\s*)?\d+[\s\.\-\)]+', '', t, flags=re.IGNORECASE)
    # Minúsculas
    t = t.lower()
    # Quitar acentos (NFKD decomposition)
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    # Colapsar espacios
    return re.sub(r'\s+', ' ', t).strip()


def _match_promovida(conn, isrc: str, artista: str, titulo: str) -> Optional[dict]:
    """
    Busca la promovida activa que coincide con el play recibido.
    Primero por ISRC exacto; si no, por título normalizado.
    Retorna dict con {id, tarifa_venue, creditos_total, creditos_usados} o None.
    """
    promos = conn.execute(
        """SELECT id, isrc, artista_nombre, titulo, tarifa_venue,
                  creditos_total, creditos_usados
           FROM canciones_promovidas WHERE activa=1"""
    ).fetchall()

    norm_query = _normalize_title(titulo)

    for p in promos:
        # Coincidencia por ISRC (si ambos tienen ISRC)
        if isrc and p['isrc'] and isrc.upper() == p['isrc'].upper():
            return dict(p)
        # Coincidencia por título normalizado (sin exigir mismo artista)
        if norm_query and _normalize_title(p['titulo']) == norm_query:
            return dict(p)

    return None


@app.post("/v1/plays", status_code=201)
async def receive_plays(
    payload: PlaysPayload,
    x_api_key: str = Header(alias="X-API-Key", default="")
):
    """Recibe lote de plays desde la app. Requiere API key válida."""
    if not payload.plays:
        return {"accepted": [], "total": 0}

    # Validar API key con el venue_id del primer play
    first = payload.plays[0]
    venue = verify_api_key(first.venue_id, x_api_key)
    if not venue:
        raise HTTPException(status_code=401, detail="API key inválida")

    accepted = []
    with get_conn(PLAYS_DB) as conn:
        cfg = get_system_config(conn)
        umbral = cfg.get("umbral_pct", 80)

        for play in payload.plays:
            try:
                result = conn.execute("""
                    INSERT OR IGNORE INTO plays
                    (idempotency_key, timestamp, venue_id, fuente, contenido, artista, titulo,
                     duracion, isrc, isrc_fuente, in_catalog,
                     porcentaje, segundos_escuchados, duracion_seg, confianza)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    play.idempotency_key, play.timestamp, play.venue_id,
                    play.fuente, play.contenido, play.artista, play.titulo,
                    play.duracion, play.isrc, play.isrc_fuente, 1 if play.in_catalog else 0,
                    play.porcentaje, play.segundos_escuchados, play.duracion_seg, play.confianza
                ))
                inserted = result.rowcount > 0
                accepted.append(play.idempotency_key)

                # Si el play es efectivo (≥ umbral) y fue nuevo (no duplicado),
                # buscar si coincide con una canción promovida y descontar crédito
                if inserted and play.porcentaje >= umbral:
                    promo = _match_promovida(conn, play.isrc or "", play.artista, play.titulo)
                    if promo:
                        # Marcar el play con el ID de la promovida (para reportes)
                        conn.execute(
                            "UPDATE plays SET promovida_id = ? WHERE idempotency_key = ?",
                            (promo['id'], play.idempotency_key)
                        )
                        # Solo descontar crédito si quedan disponibles
                        if promo['creditos_usados'] < promo['creditos_total']:
                            conn.execute(
                                "UPDATE canciones_promovidas SET creditos_usados = creditos_usados + 1 WHERE id = ?",
                                (promo['id'],)
                            )
                            log.info(
                                f"[Promovida] '{play.titulo}' → '{promo['titulo']}' "
                                f"({promo['creditos_usados']+1}/{promo['creditos_total']}) "
                                f"venue={play.venue_id}"
                            )
                        else:
                            log.info(f"[Promovida] '{promo['titulo']}' sin créditos restantes, play marcado sin descontar")

            except Exception as e:
                log.error(f"[Plays] Error insertando play {play.idempotency_key}: {e}")

    log.info(f"[Plays] Recibidos: {len(accepted)}/{len(payload.plays)} para venue {first.venue_id}")

    # Retornar cuáles plays son de canciones promovidas (para que el cliente actualice su DB local)
    promovidas_keys = []
    if accepted:
        with get_conn(PLAYS_DB) as conn:
            placeholders = ",".join("?" for _ in accepted)
            rows = conn.execute(
                f"SELECT idempotency_key FROM plays WHERE idempotency_key IN ({placeholders}) AND promovida_id IS NOT NULL",
                accepted
            ).fetchall()
            promovidas_keys = [r[0] for r in rows]

    return {"accepted": accepted, "total": len(accepted), "promovidas": promovidas_keys}


@app.get("/v1/plays/{venue_id}")
async def get_plays(
    venue_id: str,
    limit: int = 100,
    x_api_key: str = Header(alias="X-API-Key", default="")
):
    """Devuelve los plays recientes de un venue (para el dashboard)."""
    venue = verify_api_key(venue_id, x_api_key)
    if not venue:
        raise HTTPException(status_code=401, detail="API key inválida")

    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute("""
            SELECT artista, titulo, isrc, isrc_fuente, in_catalog,
                   porcentaje, duracion_seg, confianza, created_at
            FROM plays WHERE venue_id=?
            ORDER BY created_at DESC LIMIT ?
        """, (venue_id, limit)).fetchall()

    return {"plays": [dict(r) for r in rows], "total": len(rows)}


# ── Catálogo (sync a clientes) ─────────────────────────────────────────────────

@app.get("/v1/catalog/version")
async def catalog_version(x_api_key: str = Header(alias="X-API-Key", default="")):
    """
    Versión actual del catálogo de fingerprints.
    Los clientes la consultan al arrancar y cada 6h para saber si deben sincronizar.
    No requiere venue_id — cualquier API key válida de cualquier venue sirve.
    """
    # Validar que sea una API key conocida (cualquier venue)
    with get_conn(VENUES_DB) as conn:
        row = conn.execute(
            "SELECT id FROM venues WHERE api_key=? AND activo=1", (x_api_key,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="API key inválida")

    if not _fp_index:
        return {"version": 0, "count": 0}

    version = max(e["updated_ts"] for e in _fp_index)
    return {"version": version, "count": len(_fp_index)}


def _get_inactive_tombstones(since: int = 0) -> list:
    """Return inactive track IDs as tombstones so clients can deactivate them locally."""
    if not os.path.exists(FINGERPRINTS_DB):
        return []
    try:
        with get_conn(FINGERPRINTS_DB) as conn:
            query = "SELECT id FROM tracks WHERE active=0"
            params = ()
            if since:
                query += " AND CAST(updated_at AS INTEGER) > ?"
                params = (since,)
            rows = conn.execute(query, params).fetchall()
        return [
            {"id": r["id"], "artista": "", "titulo": "", "isrc": "",
             "duration_seg": 0, "fp_raw": "", "active": False,
             "updated_at": 0, "is_promovida": False}
            for r in rows
        ]
    except Exception as exc:
        log.warning(f"[Catalog] Error fetching tombstones: {exc}")
        return []


@app.get("/v1/catalog/full")
async def catalog_full(x_api_key: str = Header(alias="X-API-Key", default="")):
    """
    Catálogo completo para descarga inicial.
    Devuelve tracks activos (con fingerprint) + tombstones inactivos (sin fp).
    Los clientes marcan los tombstones como active=0 localmente.
    """
    with get_conn(VENUES_DB) as conn:
        row = conn.execute(
            "SELECT id FROM venues WHERE api_key=? AND activo=1", (x_api_key,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="API key inválida")

    if not _fp_index:
        return {"version": 0, "count": 0, "tracks": []}

    version = max(e["updated_ts"] for e in _fp_index)
    promo_ids = {e["id"] for e in _fp_index_promovidas}
    tracks = [
        {
            "id":           e["id"],
            "artista":      e["artista"],
            "titulo":       e["titulo"],
            "isrc":         e["isrc"],
            "duration_seg": e["duration"],
            "fp_raw":       e["fp_raw_b64"],
            "active":       e["active"],
            "updated_at":   e["updated_ts"],
            "is_promovida": e["id"] in promo_ids,
        }
        for e in _fp_index
    ]
    tombstones = _get_inactive_tombstones()
    all_tracks = tracks + tombstones
    log.info(f"[Catalog] Full download — {len(tracks)} tracks + {len(tombstones)} tombstones ({len(promo_ids)} promovidas)")
    return {"version": version, "count": len(all_tracks), "tracks": all_tracks}


@app.get("/v1/catalog/delta")
async def catalog_delta(
    since: int = 0,
    x_api_key: str = Header(alias="X-API-Key", default="")
):
    """
    Actualización incremental desde `since` (unix timestamp).
    Solo devuelve tracks creados/modificados después de `since`.
    Los clientes pasan su `version` local como `since`.
    """
    with get_conn(VENUES_DB) as conn:
        row = conn.execute(
            "SELECT id FROM venues WHERE api_key=? AND activo=1", (x_api_key,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="API key inválida")

    if not _fp_index:
        return {"version": 0, "count": 0, "tracks": []}

    version = max(e["updated_ts"] for e in _fp_index)
    promo_ids = {e["id"] for e in _fp_index_promovidas}
    tracks = [
        {
            "id":           e["id"],
            "artista":      e["artista"],
            "titulo":       e["titulo"],
            "isrc":         e["isrc"],
            "duration_seg": e["duration"],
            "fp_raw":       e["fp_raw_b64"],
            "active":       e["active"],
            "updated_at":   e["updated_ts"],
            "is_promovida": e["id"] in promo_ids,
        }
        for e in _fp_index
        if e["updated_ts"] > since
    ]
    tombstones = _get_inactive_tombstones(since)
    all_tracks = tracks + tombstones
    log.info(f"[Catalog] Delta since={since} — {len(tracks)} tracks + {len(tombstones)} tombstones")
    return {"version": version, "count": len(all_tracks), "tracks": all_tracks}


# ── Admin: activar/desactivar tracks del catálogo ─────────────────────────────

@app.patch("/admin/catalog/{track_id}")
async def set_track_active(track_id: int, active: bool):
    """
    Activa o desactiva un track del ciclo de pagos.
    El fingerprint siempre queda para identificación; `active` solo controla
    si el play se reporta como in_catalog=True.
    """
    if not os.path.exists(FINGERPRINTS_DB):
        raise HTTPException(status_code=503, detail="fingerprints.db no disponible")
    with get_conn(FINGERPRINTS_DB) as conn:
        conn.execute(
            "UPDATE tracks SET active=?, updated_at=datetime('now') WHERE id=?",
            (1 if active else 0, track_id)
        )
    # Recargar índice en background para que los cambios surtan efecto
    import threading
    def _reload_fp():
        load_fp_index()
        load_fp_index_promovidas()
    threading.Thread(target=_reload_fp, daemon=True).start()
    return {"ok": True, "track_id": track_id, "active": active}


# ── Admin endpoints ────────────────────────────────────────────────────────────

@app.get("/admin/venues")
async def list_venues():
    """Lista todos los venues (sin autenticación por ahora — agregar auth admin)."""
    with get_conn(VENUES_DB) as conn:
        rows = conn.execute("SELECT id, nombre, ciudad, activo, created_at FROM venues").fetchall()
    return {"venues": [dict(r) for r in rows]}


@app.post("/admin/venues")
async def create_venue(nombre: str, ciudad: str = "", venue_id: str = ""):
    """Crea un nuevo venue con un API key aleatorio."""
    import secrets
    if not venue_id:
        venue_id = f"VENUE-{secrets.token_hex(3).upper()}"
    api_key = secrets.token_urlsafe(32)

    with get_conn(VENUES_DB) as conn:
        conn.execute(
            "INSERT INTO venues (id, nombre, ciudad, api_key) VALUES (?,?,?,?)",
            (venue_id, nombre, ciudad, api_key)
        )

    log.info(f"[Admin] Venue creado: {venue_id} — {nombre}")
    return {"venue_id": venue_id, "api_key": api_key, "nombre": nombre}


# ── Stats ──────────────────────────────────────────────────────────────────────

@app.get("/admin/global_stats")
async def get_global_stats():
    """Estadísticas globales del sistema (uso interno)."""
    with get_conn(PLAYS_DB) as conn:
        total = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
        in_catalog = conn.execute("SELECT COUNT(*) FROM plays WHERE in_catalog=1").fetchone()[0]
        with_isrc = conn.execute("SELECT COUNT(*) FROM plays WHERE isrc != ''").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM plays WHERE DATE(created_at)=DATE('now')"
        ).fetchone()[0]
    return {
        "total_plays":  total,
        "in_catalog":   in_catalog,
        "with_isrc":    with_isrc,
        "today":        today,
        "catalog_rate": round(in_catalog / total * 100, 1) if total > 0 else 0,
    }


@app.get("/admin/stats")
async def admin_stats_compat(
    mes:      str = "",
    fecha:    str = "",
    hasta:    str = "",
    id_local: str = "",
    fuente:   str = "",
    buscar:   str = "",
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    """Estadísticas por venue — formato compatible con el dashboard antiguo."""
    # Construir filtro de fecha
    if mes:
        date_filter = f"AND created_at >= '{mes}-01' AND created_at < date('{mes}-01', '+1 month')"
    elif fecha and hasta:
        date_filter = f"AND DATE(created_at) >= '{fecha[:10]}' AND DATE(created_at) <= '{hasta}'"
    elif fecha:
        date_filter = f"AND DATE(created_at) = '{fecha[:10]}'"
    else:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        date_filter = f"AND created_at >= '{month}-01'"

    local_filter  = f"AND venue_id = '{id_local}'"  if id_local else ""
    fuente_filter = f"AND fuente = '{fuente}'"       if fuente   else ""

    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(f"""
            SELECT venue_id,
                   COUNT(*) as total_plays,
                   SUM(CASE WHEN promovida_id IS NOT NULL THEN 1 ELSE 0 END) as plays_cpm,
                   GROUP_CONCAT(DISTINCT fuente) as fuentes_raw
            FROM plays
            WHERE 1=1 {date_filter} {local_filter} {fuente_filter}
            GROUP BY venue_id
        """).fetchall()

    with get_conn(VENUES_DB) as conn:
        venues = {r["id"]: dict(r) for r in conn.execute(
            "SELECT id, nombre, ciudad FROM venues"
        ).fetchall()}

    result = []
    for r in rows:
        v = venues.get(r["venue_id"], {})
        fuentes = [f for f in (r["fuentes_raw"] or "").split(",") if f]
        result.append({
            "id_local":    r["venue_id"],
            "id":          r["venue_id"],
            "nombre":      v.get("nombre", r["venue_id"]),
            "ciudad":      v.get("ciudad", ""),
            "total_plays": r["total_plays"],
            "plays_cpm":   r["plays_cpm"],
            "fuentes":     fuentes,
        })

    # Si se filtró por un local y no tiene plays, igual devolverlo
    if id_local and not result:
        v = venues.get(id_local, {})
        result.append({"id_local": id_local, "id": id_local,
                        "nombre": v.get("nombre", id_local), "ciudad": v.get("ciudad", ""),
                        "total_plays": 0, "plays_cpm": 0, "fuentes": []})
    return result


# ── HTML Dashboard constants ───────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SumarteRed — Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  :root { --sr: #1C9FBD; --sr-dark: #147a93; --sr-light: #e0f7fb; }
  * { box-sizing: border-box; }
  body { font-family: system-ui,-apple-system,sans-serif; background:#f1f5f9; margin:0; display:flex; min-height:100vh; }

  /* Sidebar */
  #sidebar { width:220px; min-height:100vh; background:#0f172a; display:flex; flex-direction:column; flex-shrink:0; }
  #sidebar .logo { padding:24px 20px 20px; border-bottom:1px solid #1e293b; }
  #sidebar .logo .brand { font-size:17px; font-weight:700; color:#fff; letter-spacing:-0.3px; }
  #sidebar .logo .sub   { font-size:11px; color:#64748b; margin-top:2px; }
  #sidebar nav { padding:12px 10px; flex:1; }
  #sidebar nav a {
    display:flex; align-items:center; gap:10px; padding:9px 12px; border-radius:8px;
    color:#94a3b8; font-size:13.5px; font-weight:500; cursor:pointer;
    text-decoration:none; margin-bottom:2px; transition:background .15s,color .15s;
  }
  #sidebar nav a:hover { background:#1e293b; color:#e2e8f0; }
  #sidebar nav a.active { background:#1C9FBD22; color:#3bb8d0; }
  #sidebar nav a .icon { width:16px; text-align:center; flex-shrink:0; }
  #sidebar .sidebar-footer { padding:16px; border-top:1px solid #1e293b; }
  #sidebar .sidebar-footer span { font-size:11px; color:#475569; }

  /* Main */
  #main { flex:1; display:flex; flex-direction:column; min-width:0; }
  #topbar { background:#fff; border-bottom:1px solid #e2e8f0; padding:0 24px; height:56px;
            display:flex; align-items:center; justify-content:space-between; flex-shrink:0; }
  #topbar h1 { font-size:15px; font-weight:600; color:#0f172a; }
  #topbar .topbar-right { display:flex; align-items:center; gap:12px; }
  #content { padding:24px; flex:1; }

  /* Stats */
  .stat-card { background:#fff; border-radius:12px; padding:18px 20px; border:1px solid #e2e8f0; }
  .stat-card .val { font-size:28px; font-weight:700; line-height:1; margin-bottom:4px; }
  .stat-card .lbl { font-size:12px; color:#64748b; font-weight:500; }

  /* Tables */
  .card { background:#fff; border-radius:12px; border:1px solid #e2e8f0; overflow:hidden; }
  .card-header { padding:16px 20px; border-bottom:1px solid #f1f5f9; display:flex; align-items:center; justify-content:space-between; }
  .card-header h2 { font-size:14px; font-weight:600; color:#0f172a; margin:0; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead tr { background:#f8fafc; }
  thead th { padding:10px 16px; text-align:left; font-size:11px; font-weight:600; color:#64748b; text-transform:uppercase; letter-spacing:.5px; }
  tbody tr { border-top:1px solid #f1f5f9; transition:background .1s; }
  tbody tr:hover { background:#f8fafc; }
  tbody td { padding:11px 16px; color:#374151; }

  /* Badges */
  .badge { display:inline-flex; align-items:center; padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; }
  .badge-green  { background:#dcfce7; color:#166534; }
  .badge-gray   { background:#f1f5f9; color:#64748b; }
  .badge-yellow { background:#fef9c3; color:#854d0e; }
  .badge-blue   { background:#dbeafe; color:#1e40af; }

  /* Progress bar */
  .progress-wrap { height:4px; background:#e2e8f0; border-radius:9999px; overflow:hidden; width:80px; display:inline-block; vertical-align:middle; margin-left:6px; }
  .progress-fill { height:100%; border-radius:9999px; background:var(--sr); }

  /* Buttons */
  .btn-primary { background:var(--sr); color:#fff; border:none; padding:8px 16px; border-radius:8px; font-size:13px; font-weight:500; cursor:pointer; transition:background .15s; }
  .btn-primary:hover { background:var(--sr-dark); }
  .btn-ghost { background:transparent; border:1px solid #e2e8f0; color:#374151; padding:7px 14px; border-radius:8px; font-size:13px; cursor:pointer; transition:background .15s; }
  .btn-ghost:hover { background:#f8fafc; }
  .btn-danger { background:#fee2e2; color:#991b1b; border:none; padding:5px 10px; border-radius:6px; font-size:11px; cursor:pointer; }
  .btn-sm { padding:5px 10px; font-size:11px; border-radius:6px; }

  /* Sections */
  .section { display:none; }
  .section.visible { display:block; }

  /* Modal */
  .modal-bg { display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:50; align-items:center; justify-content:center; }
  .modal-bg.open { display:flex; }
  .modal-box { background:#fff; border-radius:16px; width:100%; max-width:480px; margin:16px; padding:24px; box-shadow:0 20px 60px rgba(0,0,0,.15); }
  .modal-title { font-size:16px; font-weight:700; color:#0f172a; margin:0 0 16px; }
  .field label { display:block; font-size:11px; font-weight:600; color:#64748b; margin-bottom:5px; text-transform:uppercase; letter-spacing:.4px; }
  .field input, .field select { width:100%; border:1.5px solid #e2e8f0; border-radius:8px; padding:9px 12px; font-size:13px; outline:none; transition:border .15s; background:#fff; }
  .field input:focus, .field select:focus { border-color:var(--sr); }
  .field { margin-bottom:14px; }

  /* Refresh dot */
  .live-dot { width:7px; height:7px; background:#10b981; border-radius:50%; display:inline-block; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  /* Plays progress row */
  .plays-bar { display:flex; align-items:center; gap:6px; }
  .plays-bar .count { font-weight:600; color:#0f172a; min-width:30px; font-size:13px; }
  .plays-bar .total { font-size:11px; color:#94a3b8; }

  /* Truncate */
  .trunc { max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sidebar">
  <div class="logo">
    <div class="brand">SumarteRed</div>
    <div class="sub">Panel de Administración</div>
  </div>
  <nav>
    <a class="active" onclick="showSection('promovidas',this)">
      <span class="icon">★</span> Promovidas
    </a>
    <a onclick="showSection('monitoreo',this)">
      <span class="icon">◎</span> Monitoreo en vivo
    </a>
    <a onclick="showSection('artistas',this)">
      <span class="icon">♪</span> Artistas
    </a>
    <a onclick="showSection('venues',this)">
      <span class="icon">⌂</span> Venues
    </a>
  </nav>
  <div class="sidebar-footer">
    <span>v3.1 · SumarteRed</span>
  </div>
</div>

<!-- Main content -->
<div id="main">
  <!-- Top bar -->
  <div id="topbar">
    <h1 id="topbar-title">Canciones Promovidas</h1>
    <div class="topbar-right">
      <span class="live-dot"></span>
      <span style="font-size:12px;color:#64748b;">En vivo</span>
      <button class="btn-ghost btn-sm" onclick="refreshAll()">↻ Actualizar</button>
    </div>
  </div>

  <!-- Content -->
  <div id="content">

    <!-- Stats -->
    <div id="stats-bar" style="display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:24px;">
      <div class="stat-card"><div class="val" style="color:#1C9FBD">—</div><div class="lbl">Plays hoy</div></div>
      <div class="stat-card"><div class="val" style="color:#10b981">—</div><div class="lbl">Efectivos hoy</div></div>
      <div class="stat-card"><div class="val" style="color:#7c3aed">—</div><div class="lbl">Venues activos</div></div>
      <div class="stat-card"><div class="val" style="color:#f59e0b">—</div><div class="lbl">Artistas</div></div>
      <div class="stat-card"><div class="val" style="color:#ec4899">—</div><div class="lbl">Promovidas activas</div></div>
    </div>

    <!-- PROMOVIDAS -->
    <div id="section-promovidas" class="section visible">
      <div class="card">
        <div class="card-header">
          <h2>Canciones Promovidas</h2>
          <button class="btn-primary" onclick="openModalPromovida()">+ Nueva canción</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Artista / Título</th>
              <th>ISRC</th>
              <th>Género</th>
              <th style="text-align:center">Plays</th>
              <th style="text-align:center">Créditos</th>
              <th style="text-align:center">Tarifa</th>
              <th style="text-align:center">Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="tbl-promovidas">
            <tr><td colspan="8" style="text-align:center;padding:32px;color:#94a3b8;">Cargando...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- MONITOREO -->
    <div id="section-monitoreo" class="section">
      <div class="card">
        <div class="card-header">
          <h2>Reproducciones en tiempo real</h2>
          <span style="font-size:12px;color:#64748b;">Últimas 200 · auto-refresh 30s</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Hora</th>
              <th>Venue</th>
              <th>Artista / Título</th>
              <th>ISRC</th>
              <th style="text-align:center">%</th>
              <th style="text-align:center">Catálogo</th>
              <th style="text-align:center">Enviado</th>
            </tr>
          </thead>
          <tbody id="tbl-monitoreo">
            <tr><td colspan="7" style="text-align:center;padding:32px;color:#94a3b8;">Cargando...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ARTISTAS -->
    <div id="section-artistas" class="section">
      <div class="card">
        <div class="card-header">
          <h2>Artistas registrados</h2>
          <button class="btn-primary" onclick="openModalArtista()">+ Nuevo artista</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Email</th>
              <th>Teléfono</th>
              <th>Registrado</th>
              <th style="text-align:center">Promovidas</th>
            </tr>
          </thead>
          <tbody id="tbl-artistas">
            <tr><td colspan="5" style="text-align:center;padding:32px;color:#94a3b8;">Cargando...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- VENUES -->
    <div id="section-venues" class="section">
      <div class="card">
        <div class="card-header">
          <h2>Venues activos</h2>
        </div>
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>ID / API Key</th>
              <th>Ciudad</th>
              <th style="text-align:center">Estado</th>
              <th style="text-align:center">Plays CPM (mes)</th>
            </tr>
          </thead>
          <tbody id="tbl-venues">
            <tr><td colspan="5" style="text-align:center;padding:32px;color:#94a3b8;">Cargando...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<!-- ═══ MODAL: Nueva Promovida ═══ -->
<div id="modal-promovida" class="modal-bg">
  <div class="modal-box" style="max-width:520px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <h3 class="modal-title" style="margin:0">Nueva Canción Promovida</h3>
      <button onclick="closeModal('modal-promovida')" style="background:none;border:none;font-size:20px;cursor:pointer;color:#94a3b8;line-height:1">&times;</button>
    </div>
    <form id="form-promovida" onsubmit="submitPromovida(event)">
      <div class="field">
        <label>Artista</label>
        <select name="artista_sel" id="sel-artista" onchange="onArtistaChange(this)" required>
          <option value="">— Selecciona un artista —</option>
        </select>
      </div>
      <input type="hidden" name="artista_id" id="inp-artista-id">
      <input type="hidden" name="artista_nombre" id="inp-artista-nombre">
      <div class="field">
        <label>Título de la canción</label>
        <input name="titulo" required placeholder="Ej: La Bicicleta">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field">
          <label>ISRC <span style="font-weight:400;text-transform:none;color:#94a3b8">(opcional)</span></label>
          <input name="isrc" placeholder="CO-XXX-YY-ZZZZZ" style="font-family:monospace;font-size:12px">
        </div>
        <div class="field">
          <label>Género</label>
          <input name="genero" placeholder="Salsa, Vallenato, Pop...">
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field">
          <label>Créditos (plays contratados)</label>
          <input name="creditos_total" type="number" value="100" min="0">
        </div>
        <div class="field">
          <label>Tarifa venue (COP/play)</label>
          <input name="tarifa_venue" type="number" value="500" min="0">
        </div>
      </div>
      <div id="err-promovida" style="color:#dc2626;font-size:12px;margin-bottom:10px;display:none"></div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px">
        <button type="button" class="btn-ghost" onclick="closeModal('modal-promovida')">Cancelar</button>
        <button type="submit" class="btn-primary">Guardar canción</button>
      </div>
    </form>
  </div>
</div>

<!-- ═══ MODAL: Nuevo Artista ═══ -->
<div id="modal-artista" class="modal-bg">
  <div class="modal-box" style="max-width:420px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <h3 class="modal-title" style="margin:0">Nuevo Artista</h3>
      <button onclick="closeModal('modal-artista')" style="background:none;border:none;font-size:20px;cursor:pointer;color:#94a3b8;line-height:1">&times;</button>
    </div>
    <form id="form-artista" onsubmit="submitArtista(event)">
      <div class="field">
        <label>Nombre artístico</label>
        <input name="nombre" required placeholder="Nombre como aparece en catálogo">
      </div>
      <div class="field">
        <label>Email</label>
        <input name="email" type="email" placeholder="contacto@artista.com">
      </div>
      <div class="field">
        <label>Teléfono / WhatsApp</label>
        <input name="telefono" placeholder="+57 300 000 0000">
      </div>
      <div id="err-artista" style="color:#dc2626;font-size:12px;margin-bottom:10px;display:none"></div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px">
        <button type="button" class="btn-ghost" onclick="closeModal('modal-artista')">Cancelar</button>
        <button type="submit" class="btn-primary">Registrar artista</button>
      </div>
    </form>
  </div>
</div>

<script>
// ── Navegación ────────────────────────────────────────────────────────────────
const SECTION_TITLES = {
  promovidas: 'Canciones Promovidas',
  monitoreo:  'Monitoreo en Tiempo Real',
  artistas:   'Artistas',
  venues:     'Venues'
};

function showSection(name, el) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('visible'));
  document.querySelectorAll('#sidebar nav a').forEach(a => a.classList.remove('active'));
  document.getElementById('section-' + name).classList.add('visible');
  el.classList.add('active');
  document.getElementById('topbar-title').textContent = SECTION_TITLES[name] || name;
}

// ── Modales ───────────────────────────────────────────────────────────────────
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

async function openModalPromovida() {
  // Cargar artistas en el select
  const sel = document.getElementById('sel-artista');
  sel.innerHTML = '<option value="">— Selecciona un artista —</option>';
  try {
    const r = await fetch('/v1/artistas');
    const arts = await r.json();
    arts.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = a.nombre;
      opt.dataset.nombre = a.nombre;
      sel.appendChild(opt);
    });
  } catch(e) {}
  document.getElementById('modal-promovida').classList.add('open');
}

function onArtistaChange(sel) {
  const opt = sel.options[sel.selectedIndex];
  document.getElementById('inp-artista-id').value    = opt.value || '';
  document.getElementById('inp-artista-nombre').value = opt.dataset.nombre || '';
}

function openModalArtista() {
  document.getElementById('modal-artista').classList.add('open');
}

// ── Formateo ──────────────────────────────────────────────────────────────────
function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleString('es-CO', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
}
function fmtCOP(n) { return n ? '$' + Number(n).toLocaleString('es-CO') : '—'; }

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const r = await fetch('/v1/stats/admin');
    if (!r.ok) return;
    const d = await r.json();
    const vals = [d.plays_hoy, d.plays_catalogo_hoy, d.venues_activos, d.artistas, d.promovidas_activas];
    document.querySelectorAll('#stats-bar .val').forEach((el, i) => el.textContent = vals[i] ?? 0);
  } catch(e) {}
}

// ── Promovidas ────────────────────────────────────────────────────────────────
async function loadPromovidas() {
  const tbody = document.getElementById('tbl-promovidas');
  try {
    const r = await fetch('/v1/promovidas');
    const data = await r.json();
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:#94a3b8;">Sin canciones promovidas · usa el botón "+ Nueva canción" para agregar</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(p => {
      const pct = p.creditos_total > 0 ? Math.min(Math.round((p.plays_efectivos / p.creditos_total) * 100), 100) : 0;
      const barColor = pct >= 100 ? '#ef4444' : pct >= 75 ? '#f59e0b' : '#1C9FBD';
      return `<tr>
        <td>
          <div style="font-weight:600;color:#0f172a;font-size:13px" class="trunc">${p.titulo}</div>
          <div style="font-size:11px;color:#64748b">${p.artista_nombre}</div>
        </td>
        <td style="font-family:monospace;font-size:11px;color:#64748b">${p.isrc || '—'}</td>
        <td style="font-size:12px;color:#64748b">${p.genero || '—'}</td>
        <td style="text-align:center">
          <div class="plays-bar" style="justify-content:center">
            <span class="count">${p.plays_efectivos}</span>
            <div class="progress-wrap"><div class="progress-fill" style="width:${pct}%;background:${barColor}"></div></div>
          </div>
        </td>
        <td style="text-align:center;font-size:12px;color:#374151">${p.creditos_usados} / ${p.creditos_total}</td>
        <td style="text-align:center;font-size:12px;color:#374151">${fmtCOP(p.tarifa_venue)}</td>
        <td style="text-align:center">
          <span class="badge ${p.activa ? 'badge-green' : 'badge-gray'}">${p.activa ? 'Activa' : 'Pausada'}</span>
        </td>
        <td style="text-align:center">
          <button onclick="togglePromovida('${p.id}', ${!p.activa})"
            class="${p.activa ? 'btn-danger' : 'btn-ghost'} btn-sm">
            ${p.activa ? 'Pausar' : 'Activar'}
          </button>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:32px;color:#ef4444;">Error cargando datos</td></tr>'; }
}

async function togglePromovida(id, activa) {
  await fetch('/v1/promovidas/' + id, {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ activa })
  });
  loadPromovidas();
  loadStats();
}

async function submitPromovida(e) {
  e.preventDefault();
  const form = e.target;
  const errEl = document.getElementById('err-promovida');
  errEl.style.display = 'none';
  const artId = document.getElementById('inp-artista-id').value;
  if (!artId) { errEl.textContent = 'Selecciona un artista'; errEl.style.display = 'block'; return; }
  const body = {
    artista_id:    artId,
    artista_nombre: document.getElementById('inp-artista-nombre').value,
    titulo:        form.titulo.value.trim(),
    isrc:          form.isrc.value.trim(),
    genero:        form.genero.value.trim(),
    creditos_total: parseInt(form.creditos_total.value) || 0,
    tarifa_venue:  parseFloat(form.tarifa_venue.value) || 500,
  };
  try {
    const r = await fetch('/v1/promovidas', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (!r.ok) { const d = await r.json(); errEl.textContent = d.detail || 'Error'; errEl.style.display = 'block'; return; }
    closeModal('modal-promovida');
    form.reset();
    loadPromovidas(); loadStats();
  } catch(err) { errEl.textContent = err.message; errEl.style.display = 'block'; }
}

// ── Monitoreo ─────────────────────────────────────────────────────────────────
async function loadMonitoreo() {
  const tbody = document.getElementById('tbl-monitoreo');
  try {
    const r = await fetch('/v1/plays/all');
    if (!r.ok) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#94a3b8;">No disponible</td></tr>'; return; }
    const data = await r.json();
    const plays = data.plays || [];
    if (!plays.length) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#94a3b8;">Sin reproducciones registradas</td></tr>'; return; }
    tbody.innerHTML = plays.map(p => {
      const pct = Math.round(p.porcentaje || 0);
      const ok  = pct >= 80 && p.in_catalog;
      return `<tr>
        <td style="font-size:11px;color:#64748b;white-space:nowrap">${fmtDate(p.created_at)}</td>
        <td style="font-size:11px;color:#64748b;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.venue_id || '—'}</td>
        <td>
          <div style="font-weight:500;font-size:12px;color:#0f172a;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.titulo || p.contenido || '—'}</div>
          <div style="font-size:11px;color:#64748b">${p.artista || ''}</div>
        </td>
        <td style="font-family:monospace;font-size:11px;color:#64748b">${p.isrc || '—'}</td>
        <td style="text-align:center">
          <span style="font-weight:700;font-size:13px;color:${ok ? '#10b981' : pct >= 50 ? '#f59e0b' : '#94a3b8'}">${pct}%</span>
        </td>
        <td style="text-align:center"><span class="badge ${p.in_catalog ? 'badge-green' : 'badge-gray'}">${p.in_catalog ? 'Sí' : 'No'}</span></td>
        <td style="text-align:center"><span class="badge ${p.enviado ? 'badge-blue' : 'badge-yellow'}">${p.enviado ? 'Enviado' : 'Pendiente'}</span></td>
      </tr>`;
    }).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#ef4444;">Error</td></tr>'; }
}

// ── Artistas ──────────────────────────────────────────────────────────────────
let artistasCache = [];

async function loadArtistas() {
  const tbody = document.getElementById('tbl-artistas');
  try {
    const r = await fetch('/v1/artistas');
    artistasCache = await r.json();
    if (!artistasCache.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:32px;color:#94a3b8;">Sin artistas · usa "+ Nuevo artista"</td></tr>'; return; }
    // Count promovidas per artista (from current data if available)
    const promoR = await fetch('/v1/promovidas');
    const promos = await promoR.json();
    const countMap = {};
    promos.forEach(p => { countMap[p.artista_id] = (countMap[p.artista_id] || 0) + 1; });
    tbody.innerHTML = artistasCache.map(a => `
      <tr>
        <td style="font-weight:600;color:#0f172a">${a.nombre}</td>
        <td style="color:#64748b;font-size:12px">${a.email || '—'}</td>
        <td style="color:#64748b;font-size:12px">${a.telefono || '—'}</td>
        <td style="color:#94a3b8;font-size:11px">${fmtDate(a.created_at)}</td>
        <td style="text-align:center">
          <span class="badge badge-blue">${countMap[a.id] || 0}</span>
        </td>
      </tr>`).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:32px;color:#ef4444;">Error</td></tr>'; }
}

async function submitArtista(e) {
  e.preventDefault();
  const form = e.target;
  const errEl = document.getElementById('err-artista');
  errEl.style.display = 'none';
  const body = { nombre: form.nombre.value.trim(), email: form.email.value.trim(), telefono: form.telefono.value.trim() };
  try {
    const r = await fetch('/v1/artistas', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (!r.ok) { const d = await r.json(); errEl.textContent = d.detail || 'Error'; errEl.style.display = 'block'; return; }
    closeModal('modal-artista');
    form.reset();
    loadArtistas(); loadStats();
  } catch(err) { errEl.textContent = err.message; errEl.style.display = 'block'; }
}

// ── Venues ────────────────────────────────────────────────────────────────────
async function loadVenues() {
  const tbody = document.getElementById('tbl-venues');
  try {
    const [vR, sR] = await Promise.all([
      fetch('/admin/venues'),
      fetch('/admin/stats')
    ]);
    const data  = await vR.json();
    const stats = await sR.json();
    const venues = data.venues || [];
    if (!venues.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:32px;color:#94a3b8;">Sin venues registrados</td></tr>'; return; }
    // Build stats map by venue_id
    const statsMap = {};
    (Array.isArray(stats) ? stats : []).forEach(s => { statsMap[s.id] = s; });
    tbody.innerHTML = venues.map(v => {
      const s = statsMap[v.id] || {};
      const playsCpm  = s.plays_cpm  !== undefined ? s.plays_cpm  : 0;
      const totalPlay = s.total_plays !== undefined ? s.total_plays : 0;
      return `
      <tr>
        <td style="font-weight:600;color:#0f172a">${v.nombre || v.id}</td>
        <td style="font-family:monospace;font-size:10px;color:#94a3b8;max-width:180px">
          <div>${v.id}</div>
        </td>
        <td style="color:#64748b;font-size:12px">${v.ciudad || '—'}</td>
        <td style="text-align:center"><span class="badge ${v.activo ? 'badge-green' : 'badge-gray'}">${v.activo ? 'Activo' : 'Inactivo'}</span></td>
        <td style="text-align:center">
          <span class="badge badge-blue" title="${totalPlay} totales">${playsCpm}</span>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:32px;color:#ef4444;">Error</td></tr>'; }
}

// ── Refresh ───────────────────────────────────────────────────────────────────
function refreshAll() {
  loadStats();
  loadPromovidas();
  loadMonitoreo();
  loadArtistas();
  loadVenues();
}

// Auto-refresh monitoreo cada 30s
setInterval(() => {
  loadStats();
  const monitoreoVisible = document.getElementById('section-monitoreo').classList.contains('visible');
  if (monitoreoVisible) loadMonitoreo();
}, 30000);

// Carga inicial
refreshAll();
</script>
</body>
</html>"""

ARTISTA_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SumarteRed — Portal Artista</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: system-ui, sans-serif; background: #f0fafa; }
  .sr-header { background: #1C9FBD; }
  .badge-green { background:#d1fae5; color:#065f46; padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; }
  .badge-gray  { background:#f3f4f6; color:#6b7280; padding:2px 8px; border-radius:9999px; font-size:11px; }
</style>
</head>
<body>
<header class="sr-header text-white px-6 py-4 flex items-center justify-between shadow">
  <div>
    <div class="text-xl font-bold tracking-tight">SumarteRed</div>
    <div class="text-xs opacity-75" id="artista-subtitle">Portal de Artista</div>
  </div>
</header>

<main class="max-w-4xl mx-auto px-4 py-6 space-y-6">

  <!-- Credits cards -->
  <div id="credits-bar" class="grid grid-cols-3 gap-4"></div>

  <!-- Canciones -->
  <div>
    <h2 class="text-lg font-semibold text-gray-800 mb-3">Mis Canciones Promovidas</h2>
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 text-xs text-gray-500 uppercase">
          <tr>
            <th class="px-4 py-3 text-left">Título</th>
            <th class="px-4 py-3 text-left">ISRC</th>
            <th class="px-4 py-3 text-left">Género</th>
            <th class="px-4 py-3 text-center">Créditos usados</th>
            <th class="px-4 py-3 text-center">Restantes</th>
            <th class="px-4 py-3 text-center">Estado</th>
          </tr>
        </thead>
        <tbody id="tbl-canciones" class="divide-y divide-gray-100">
          <tr><td colspan="6" class="px-4 py-6 text-center text-gray-400">Cargando...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Links -->
  <div id="links-section"></div>

</main>

<script>
const ARTISTA_ID = '__ARTISTA_ID__';

async function load() {
  try {
    const [pRes, aRes] = await Promise.all([
      fetch('/v1/promovidas'),
      fetch('/v1/artistas')
    ]);
    const promovidas = await pRes.json();
    const artistas   = await aRes.json();

    const artista = artistas.find(a => a.id === ARTISTA_ID);
    if (artista) {
      document.getElementById('artista-subtitle').textContent = artista.nombre;
    }

    const mis = promovidas.filter(p => p.artista_id === ARTISTA_ID);

    // Credits
    const totalC  = mis.reduce((s, p) => s + (p.creditos_total || 0), 0);
    const usadosC = mis.reduce((s, p) => s + (p.creditos_usados || 0), 0);
    const restC   = totalC - usadosC;
    const bar = document.getElementById('credits-bar');
    bar.innerHTML = [
      ['Créditos Totales', totalC, '#1C9FBD'],
      ['Créditos Usados',  usadosC, '#d97706'],
      ['Créditos Restantes', restC, '#059669'],
    ].map(([l,v,c]) => `
      <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 text-center">
        <div class="text-3xl font-bold" style="color:${c}">${v}</div>
        <div class="text-xs text-gray-500 mt-2">${l}</div>
      </div>`).join('');

    // Table
    const tbody = document.getElementById('tbl-canciones');
    if (!mis.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-gray-400">Sin canciones promovidas</td></tr>';
      return;
    }
    tbody.innerHTML = mis.map(p => {
      const restante = (p.creditos_total || 0) - (p.creditos_usados || 0);
      const links = [p.link_spotify ? `<a href="${p.link_spotify}" target="_blank" class="text-green-600 hover:underline text-xs">Spotify</a>` : '',
                     p.link_youtube ? `<a href="${p.link_youtube}" target="_blank" class="text-red-500 hover:underline text-xs">YouTube</a>` : ''].filter(Boolean).join(' · ');
      return `<tr class="hover:bg-gray-50">
        <td class="px-4 py-3">
          <div class="font-medium text-gray-800">${p.titulo}</div>
          ${links ? '<div class="mt-1">' + links + '</div>' : ''}
        </td>
        <td class="px-4 py-3 font-mono text-xs text-gray-600">${p.isrc || '—'}</td>
        <td class="px-4 py-3 text-xs text-gray-600">${p.genero || '—'}</td>
        <td class="px-4 py-3 text-center text-sm font-semibold text-amber-600">${p.creditos_usados}</td>
        <td class="px-4 py-3 text-center text-sm font-semibold text-green-600">${restante}</td>
        <td class="px-4 py-3 text-center">
          <span class="${p.activa ? 'badge-green' : 'badge-gray'}">${p.activa ? 'Activa' : 'Inactiva'}</span>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { console.error(e); }
}

load();
</script>
</body>
</html>"""

VENUE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SumarteRed — Portal Venue</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: system-ui, sans-serif; background: #f0fafa; }
  .sr-header { background: #1C9FBD; }
  .badge-green { background:#d1fae5; color:#065f46; padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; }
  .badge-gray  { background:#f3f4f6; color:#6b7280; padding:2px 8px; border-radius:9999px; font-size:11px; }
</style>
</head>
<body>
<header class="sr-header text-white px-6 py-4 flex items-center justify-between shadow">
  <div>
    <div class="text-xl font-bold tracking-tight">SumarteRed</div>
    <div class="text-xs opacity-75">Dashboard Venue — __VENUE_ID__</div>
  </div>
  <button onclick="load()" class="text-xs bg-white bg-opacity-20 hover:bg-opacity-30 px-3 py-1.5 rounded-lg transition">
    Actualizar
  </button>
</header>

<main class="max-w-4xl mx-auto px-4 py-6 space-y-6">

  <!-- Stats cards -->
  <div id="stats-bar" class="grid grid-cols-2 md:grid-cols-4 gap-4">
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 text-center">
      <div class="text-3xl font-bold text-[#1C9FBD]" id="s-plays-hoy">—</div>
      <div class="text-xs text-gray-500 mt-2">Plays hoy</div>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 text-center">
      <div class="text-3xl font-bold text-green-600" id="s-efec-hoy">—</div>
      <div class="text-xs text-gray-500 mt-2">Efectivos hoy (≥80%)</div>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 text-center">
      <div class="text-3xl font-bold text-purple-600" id="s-plays-mes">—</div>
      <div class="text-xs text-gray-500 mt-2">Plays este mes</div>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 text-center">
      <div class="text-3xl font-bold text-emerald-600" id="s-ganancias">—</div>
      <div class="text-xs text-gray-500 mt-2">Ganancias est. (mes)</div>
    </div>
  </div>

  <!-- Canciones promovidas disponibles -->
  <div>
    <h2 class="text-lg font-semibold text-gray-800 mb-3">Canciones Promovidas Disponibles</h2>
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 text-xs text-gray-500 uppercase">
          <tr>
            <th class="px-4 py-3 text-left">Artista / Título</th>
            <th class="px-4 py-3 text-left">ISRC</th>
            <th class="px-4 py-3 text-left">Género</th>
            <th class="px-4 py-3 text-center">Tarifa</th>
            <th class="px-4 py-3 text-center">Links</th>
          </tr>
        </thead>
        <tbody id="tbl-promovidas" class="divide-y divide-gray-100">
          <tr><td colspan="5" class="px-4 py-6 text-center text-gray-400">Cargando...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Reproducciones recientes -->
  <div>
    <h2 class="text-lg font-semibold text-gray-800 mb-3">Mis Reproducciones Recientes</h2>
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 text-xs text-gray-500 uppercase">
          <tr>
            <th class="px-4 py-3 text-left">Hora</th>
            <th class="px-4 py-3 text-left">Fuente</th>
            <th class="px-4 py-3 text-left">Artista / Título</th>
            <th class="px-4 py-3 text-left">ISRC</th>
            <th class="px-4 py-3 text-center">%</th>
            <th class="px-4 py-3 text-center">Catálogo</th>
          </tr>
        </thead>
        <tbody id="tbl-plays" class="divide-y divide-gray-100">
          <tr><td colspan="6" class="px-4 py-6 text-center text-gray-400">Cargando...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

</main>

<script>
const VENUE_ID = '__VENUE_ID__';
const TARIFA   = 500;

function fmtDate(s) {
  if (!s) return '—';
  try { return new Date(s).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}); } catch(e) { return s; }
}

function fmtCOP(n) {
  return '$' + Math.round(n).toLocaleString('es-CO') + ' COP';
}

async function load() {
  await Promise.all([loadStats(), loadPromovidas()]);
}

async function loadStats() {
  try {
    const r = await fetch('/v1/stats/' + VENUE_ID);
    if (!r.ok) return;
    const d = await r.json();

    document.getElementById('s-plays-hoy').textContent = d.plays_hoy ?? '—';
    document.getElementById('s-efec-hoy').textContent  = d.efectivos_hoy ?? '—';
    document.getElementById('s-plays-mes').textContent = d.plays_mes ?? '—';
    document.getElementById('s-ganancias').textContent = fmtCOP((d.efectivos_mes || 0) * TARIFA);

    const tbody = document.getElementById('tbl-plays');
    const plays = d.historial || [];
    if (!plays.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-gray-400">Sin reproducciones</td></tr>';
      return;
    }
    tbody.innerHTML = plays.map(p => {
      const pct = ((p.porcentaje || 0)).toFixed(0);
      const pctColor = pct >= 80 ? 'text-green-600 font-bold' : 'text-gray-400';
      return `<tr class="hover:bg-gray-50 ${pct >= 80 ? 'bg-green-50' : ''}">
        <td class="px-4 py-2 text-xs font-mono text-gray-500">${fmtDate(p.hora)}</td>
        <td class="px-4 py-2 text-xs text-gray-600">${p.fuente || '—'}</td>
        <td class="px-4 py-2">
          <div class="font-medium text-xs text-gray-800">${p.titulo || '—'}</div>
          <div class="text-xs text-gray-400">${p.artista || ''}</div>
        </td>
        <td class="px-4 py-2 font-mono text-xs text-gray-500">${p.isrc || '—'}</td>
        <td class="px-4 py-2 text-center text-xs ${pctColor}">${pct}%</td>
        <td class="px-4 py-2 text-center">
          <span class="${p.en_catalogo ? 'badge-green' : 'badge-gray'}">${p.en_catalogo ? 'Sí' : 'No'}</span>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { console.error(e); }
}

async function loadPromovidas() {
  try {
    const r = await fetch('/v1/promovidas');
    const data = await r.json();
    const tbody = document.getElementById('tbl-promovidas');
    const activas = data.filter(p => p.activa);
    if (!activas.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-6 text-center text-gray-400">Sin canciones promovidas</td></tr>';
      return;
    }
    tbody.innerHTML = activas.map(p => {
      const links = [
        p.link_spotify ? `<a href="${p.link_spotify}" target="_blank" class="text-green-600 hover:underline text-xs">Spotify</a>` : '',
        p.link_youtube ? `<a href="${p.link_youtube}" target="_blank" class="text-red-500 hover:underline text-xs">YouTube</a>` : '',
      ].filter(Boolean).join(' · ');
      return `<tr class="hover:bg-gray-50">
        <td class="px-4 py-3">
          <div class="font-medium text-gray-800">${p.titulo}</div>
          <div class="text-xs text-gray-500">${p.artista_nombre}</div>
        </td>
        <td class="px-4 py-3 font-mono text-xs text-gray-600">${p.isrc || '—'}</td>
        <td class="px-4 py-3 text-xs text-gray-600">${p.genero || '—'}</td>
        <td class="px-4 py-3 text-center text-xs font-medium text-gray-700">$${p.tarifa_venue} COP</td>
        <td class="px-4 py-3 text-center">${links || '—'}</td>
      </tr>`;
    }).join('');
  } catch(e) { console.error(e); }
}

load();
</script>
</body>
</html>"""


# ── Artistas ──────────────────────────────────────────────────────────────────
@app.get("/v1/artistas")
async def list_artistas():
    conn = get_conn(PLAYS_DB)
    rows = conn.execute("SELECT id, nombre, email, telefono, created_at FROM artistas ORDER BY nombre").fetchall()
    conn.close()
    return [{"id": r[0], "nombre": r[1], "email": r[2], "telefono": r[3], "created_at": r[4]} for r in rows]

class ArtistaCreate(BaseModel):
    nombre: str
    email: str = ""
    telefono: str = ""

@app.post("/v1/artistas", status_code=201)
async def create_artista(body: ArtistaCreate):
    import uuid
    artista_id = str(uuid.uuid4())
    conn = get_conn(PLAYS_DB)
    conn.execute("INSERT INTO artistas (id, nombre, email, telefono) VALUES (?,?,?,?)",
                 (artista_id, body.nombre, body.email, body.telefono))
    conn.commit(); conn.close()
    return {"id": artista_id, "nombre": body.nombre}

# ── Canciones Promovidas ──────────────────────────────────────────────────────
class PromovidaCreate(BaseModel):
    artista_id: str
    artista_nombre: str
    titulo: str
    isrc: str = ""
    genero: str = ""
    link_spotify: str = ""
    link_youtube: str = ""
    links_otros: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = ""
    creditos_total: int = 0
    tarifa_venue: float = 500.0

@app.post("/v1/promovidas", status_code=201)
async def create_promovida(body: PromovidaCreate):
    import uuid
    promo_id = str(uuid.uuid4())
    conn = get_conn(PLAYS_DB)
    conn.execute("""
        INSERT INTO canciones_promovidas
        (id, artista_id, artista_nombre, titulo, isrc, genero,
         link_spotify, link_youtube, links_otros,
         fecha_inicio, fecha_fin, creditos_total, tarifa_venue)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (promo_id, body.artista_id, body.artista_nombre, body.titulo,
          body.isrc, body.genero, body.link_spotify, body.link_youtube,
          body.links_otros, body.fecha_inicio, body.fecha_fin,
          body.creditos_total, body.tarifa_venue))
    conn.commit(); conn.close()
    return {"id": promo_id}

@app.get("/v1/promovidas")
async def list_promovidas():
    conn = get_conn(PLAYS_DB)
    rows = conn.execute("""
        SELECT cp.id, cp.artista_id, cp.artista_nombre, cp.titulo, cp.isrc, cp.genero,
               COALESCE(NULLIF(cp.link_spotify,''), c.spotify_url, '')  AS link_spotify,
               COALESCE(NULLIF(cp.link_youtube,''), c.youtube_url, '')  AS link_youtube,
               cp.links_otros, cp.fecha_inicio, cp.fecha_fin,
               cp.creditos_total, cp.creditos_usados,
               cp.tarifa_venue, cp.activa, cp.created_at
        FROM canciones_promovidas cp
        LEFT JOIN catalogo_cpm c ON LOWER(TRIM(c.titulo)) = LOWER(TRIM(cp.titulo))
        ORDER BY cp.created_at DESC
    """).fetchall()
    keys = ["id","artista_id","artista_nombre","titulo","isrc","genero",
            "link_spotify","link_youtube","links_otros","fecha_inicio","fecha_fin",
            "creditos_total","creditos_usados","tarifa_venue","activa","created_at"]
    result = []
    for r in rows:
        d = dict(zip(keys, r))
        # activa debe ser booleano JSON (true/false), no entero, para que Swift lo decodifique
        d["activa"] = bool(d["activa"])
        # Contar plays que fueron efectivamente acreditados a esta promovida
        plays_count = conn.execute(
            "SELECT COUNT(*) FROM plays WHERE promovida_id=?",
            (d["id"],)
        ).fetchone()[0]
        d["plays_efectivos"] = plays_count
        result.append(d)
    conn.close()
    return result

@app.patch("/v1/promovidas/{promo_id}")
async def toggle_promovida(promo_id: str, body: dict):
    conn = get_conn(PLAYS_DB)
    activa = body.get("activa", True)
    conn.execute("UPDATE canciones_promovidas SET activa=? WHERE id=?", (1 if activa else 0, promo_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/v1/stats/admin")
async def admin_stats():
    conn = get_conn(PLAYS_DB)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    plays_today    = conn.execute("SELECT COUNT(*) FROM plays WHERE created_at >= ?", (today,)).fetchone()[0]
    plays_catalog  = conn.execute("SELECT COUNT(*) FROM plays WHERE created_at >= ? AND in_catalog=1 AND porcentaje>=80", (today,)).fetchone()[0]
    promovidas     = conn.execute("SELECT COUNT(*) FROM canciones_promovidas WHERE activa=1").fetchone()[0]
    artistas_count = conn.execute("SELECT COUNT(*) FROM artistas").fetchone()[0]
    conn.close()
    venues_conn  = get_conn(VENUES_DB)
    total_venues = venues_conn.execute("SELECT COUNT(*) FROM venues WHERE activo=1").fetchone()[0]
    venues_conn.close()
    return {
        "plays_hoy": plays_today,
        "plays_catalogo_hoy": plays_catalog,
        "venues_activos": total_venues,
        "artistas": artistas_count,
        "promovidas_activas": promovidas
    }

@app.get("/v1/stats/{venue_id}")
async def venue_stats(venue_id: str, x_api_key: str = Header(alias="X-API-Key", default="")):
    conn = get_conn(PLAYS_DB)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    plays_today     = conn.execute("SELECT COUNT(*) FROM plays WHERE venue_id=? AND created_at>=?",
                                    (venue_id, today)).fetchone()[0]
    effective_today = conn.execute("SELECT COUNT(*) FROM plays WHERE venue_id=? AND created_at>=? AND promovida_id IS NOT NULL",
                                    (venue_id, today)).fetchone()[0]
    plays_month     = conn.execute("SELECT COUNT(*) FROM plays WHERE venue_id=? AND created_at>=?",
                                    (venue_id, month)).fetchone()[0]
    effective_month = conn.execute("SELECT COUNT(*) FROM plays WHERE venue_id=? AND created_at>=? AND promovida_id IS NOT NULL",
                                    (venue_id, month)).fetchone()[0]
    recent = conn.execute("""SELECT timestamp, fuente, artista, titulo, isrc, duracion,
                                    segundos_escuchados, porcentaje, in_catalog, enviado
                             FROM plays WHERE venue_id=? ORDER BY created_at DESC LIMIT 50""",
                          (venue_id,)).fetchall()
    conn.close()
    return {
        "venue_id": venue_id,
        "plays_hoy": plays_today,
        "efectivos_hoy": effective_today,
        "plays_mes": plays_month,
        "efectivos_mes": effective_month,
        "historial": [
            {"hora": r[0], "fuente": r[1], "artista": r[2], "titulo": r[3],
             "isrc": r[4], "duracion": r[5], "segundos": r[6],
             "porcentaje": r[7], "en_catalogo": bool(r[8]), "enviado": bool(r[9])}
            for r in recent
        ]
    }

@app.get("/v1/plays/all")
async def get_all_plays(limit: int = 100):
    """Devuelve los plays más recientes de todos los venues (admin)."""
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute("""
            SELECT venue_id, artista, titulo, isrc, in_catalog,
                   porcentaje, duracion_seg, confianza, contenido, created_at
            FROM plays ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
    return {"plays": [dict(r) for r in rows], "total": len(rows)}


# ── HTML Dashboard routes ─────────────────────────────────────────────────────

def _read_dashboard_html() -> str:
    """Sirve dashboard.html si existe (plataforma completa); si no, ADMIN_HTML de emergencia."""
    dashboard_file = os.path.join(_SERVER_DIR, "dashboard.html")
    if os.path.exists(dashboard_file):
        with open(dashboard_file, "r", encoding="utf-8") as f:
            return f.read()
    return ADMIN_HTML


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return HTMLResponse(_read_dashboard_html())

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_alias(request: Request):
    return HTMLResponse(_read_dashboard_html())

@app.get("/artista/{artista_id}", response_class=HTMLResponse)
async def artista_dashboard(artista_id: str):
    return HTMLResponse(ARTISTA_HTML.replace("__ARTISTA_ID__", artista_id))

@app.get("/venue/{venue_id}/dashboard", response_class=HTMLResponse)
async def venue_dashboard_web(venue_id: str):
    return HTMLResponse(VENUE_HTML.replace("__VENUE_ID__", venue_id))


# ══════════════════════════════════════════════════════════════════════════════
# ── Capa de compatibilidad — Dashboard antiguo CPMTracks ─────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def _get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        with get_conn(PLAYS_DB) as conn:
            row = conn.execute("""
                SELECT u.id, u.email, u.nombre, u.rol, u.id_local
                FROM sesiones s JOIN usuarios u ON u.id = s.user_id
                WHERE s.token = ?
            """, (token,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


# ── Auth ───────────────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
async def auth_login(body: LoginBody):
    with get_conn(PLAYS_DB) as conn:
        row = conn.execute(
            "SELECT id, nombre, rol, id_local FROM usuarios WHERE email=? AND password_hash=? AND activo=1",
            (body.email, _hash_pwd(body.password))
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail={"error": "Credenciales incorrectas"})
    import secrets as _sec
    token = _sec.token_hex(32)
    with get_conn(PLAYS_DB) as conn:
        conn.execute("INSERT OR REPLACE INTO sesiones (token, user_id) VALUES (?,?)", (token, row["id"]))
    return {"session_token": token, "token": token,
            "nombre": row["nombre"], "rol": row["rol"], "id_local": row["id_local"] or ""}

@app.get("/auth/me")
async def auth_me(x_session_token: str = Header(alias="X-Session-Token", default="")):
    user = _get_user_by_token(x_session_token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    return user

@app.post("/auth/logout")
async def auth_logout(x_session_token: str = Header(alias="X-Session-Token", default="")):
    if x_session_token:
        with get_conn(PLAYS_DB) as conn:
            conn.execute("DELETE FROM sesiones WHERE token=?", (x_session_token,))
    return {"ok": True}


# ── Locales (venues) ───────────────────────────────────────────────────────────

@app.get("/v1/locales")
async def list_locales():
    """Devuelve venues en formato compatible con el dashboard antiguo."""
    with get_conn(VENUES_DB) as conn:
        rows = conn.execute("SELECT id, nombre, ciudad, activo FROM venues").fetchall()
    return {"locales": [
        {"id_local": r["id"], "nombre": r["nombre"], "tipo": "", "ciudad": r["ciudad"]}
        for r in rows if r["activo"]
    ]}

@app.get("/admin/locales")
async def admin_list_locales(x_session_token: str = Header(alias="X-Session-Token", default="")):
    with get_conn(VENUES_DB) as conn:
        rows = conn.execute("SELECT id, nombre, ciudad, api_key, activo, created_at FROM venues").fetchall()
    return [{"id_local": r["id"], "nombre": r["nombre"], "ciudad": r["ciudad"],
             "api_key": r["api_key"], "activo": bool(r["activo"])} for r in rows]

@app.post("/admin/locales", status_code=201)
async def admin_create_local(body: dict):
    import secrets as _sec
    local_id = body.get("id_local") or f"VENUE-{_sec.token_hex(3).upper()}"
    api_key  = _sec.token_urlsafe(32)
    nombre   = body.get("nombre", "")
    ciudad   = body.get("ciudad", "")
    with get_conn(VENUES_DB) as conn:
        conn.execute("INSERT OR IGNORE INTO venues (id, nombre, ciudad, api_key) VALUES (?,?,?,?)",
                     (local_id, nombre, ciudad, api_key))
    return {"id_local": local_id, "nombre": nombre, "api_key": api_key}

@app.put("/admin/locales/{local_id}")
async def admin_update_local(local_id: str, body: dict):
    fields = [k for k in ["nombre","ciudad","activo"] if k in body]
    if fields:
        sql = f"UPDATE venues SET {', '.join(f+' =?' for f in fields)} WHERE id=?"
        vals = [body[f] for f in fields] + [local_id]
        with get_conn(VENUES_DB) as conn:
            conn.execute(sql, vals)
    return {"ok": True}

@app.delete("/admin/locales/{local_id}")
async def admin_delete_local(local_id: str):
    with get_conn(VENUES_DB) as conn:
        conn.execute("UPDATE venues SET activo=0 WHERE id=?", (local_id,))
    return {"ok": True}

@app.get("/admin/locales/{local_id}")
async def admin_get_local(local_id: str):
    with get_conn(VENUES_DB) as conn:
        row = conn.execute("SELECT id, nombre, ciudad, api_key, activo FROM venues WHERE id=?", (local_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No encontrado")
    return {"id_local": row["id"], "nombre": row["nombre"], "ciudad": row["ciudad"],
            "api_key": row["api_key"], "activo": bool(row["activo"])}


# ── Usuarios ───────────────────────────────────────────────────────────────────

@app.get("/admin/usuarios")
async def admin_list_usuarios(x_session_token: str = Header(alias="X-Session-Token", default="")):
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(
            "SELECT id, email, nombre, rol, id_local, activo, created_at FROM usuarios"
        ).fetchall()
    return [dict(r) for r in rows]

@app.post("/admin/usuarios", status_code=201)
async def admin_create_usuario(body: dict):
    import uuid as _uuid
    uid = str(_uuid.uuid4())
    pwd = body.get("password") or "temporal123"
    with get_conn(PLAYS_DB) as conn:
        conn.execute(
            "INSERT INTO usuarios (id, email, nombre, rol, id_local, password_hash, activo) VALUES (?,?,?,?,?,?,?)",
            (uid, body.get("email",""), body.get("nombre",""), body.get("rol","cpm_interno"),
             body.get("id_local",""), _hash_pwd(pwd), body.get("activo", 1))
        )
    return {"id": uid, "email": body.get("email"), "nombre": body.get("nombre")}

@app.put("/admin/usuarios/{uid}")
async def admin_update_usuario(uid: str, body: dict):
    fields = [k for k in ["email","nombre","rol","id_local","activo"] if k in body]
    updates = [f + "=?" for f in fields]
    values  = [body[f] for f in fields]
    if body.get("password"):
        updates.append("password_hash=?")
        values.append(_hash_pwd(body["password"]))
    if updates:
        values.append(uid)
        with get_conn(PLAYS_DB) as conn:
            conn.execute(f"UPDATE usuarios SET {', '.join(updates)} WHERE id=?", values)
    return {"ok": True}

@app.delete("/admin/usuarios/{uid}")
async def admin_delete_usuario(uid: str):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("DELETE FROM usuarios WHERE id=?", (uid,))
    return {"ok": True}


# ── Plays list + charts ────────────────────────────────────────────────────────

def _build_date_filter(mes="", fecha="", hasta="") -> str:
    if mes:
        return f"AND created_at >= '{mes}-01' AND created_at < date('{mes}-01', '+1 month')"
    if fecha and hasta:
        return f"AND DATE(created_at) >= '{fecha[:10]}' AND DATE(created_at) <= '{hasta}'"
    if fecha:
        return f"AND DATE(created_at) = '{fecha[:10]}'"
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"AND created_at >= '{month}-01'"

@app.get("/v1/plays/list")
async def plays_list(
    limite:   int = 500,
    mes:      str = "",
    fecha:    str = "",
    hasta:    str = "",
    id_local: str = "",
    fuente:   str = "",
    buscar:   str = "",
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    df = _build_date_filter(mes, fecha, hasta)
    lf = f"AND venue_id = '{id_local}'" if id_local else ""
    ff = f"AND fuente = '{fuente}'"     if fuente   else ""
    bf = f"AND (artista LIKE '%{buscar}%' OR titulo LIKE '%{buscar}%' OR contenido LIKE '%{buscar}%')" if buscar else ""
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(f"""
            SELECT venue_id, artista, titulo, isrc, fuente, contenido,
                   porcentaje, in_catalog, created_at
            FROM plays WHERE 1=1 {df} {lf} {ff} {bf}
            ORDER BY created_at DESC LIMIT {limite}
        """).fetchall()
    return {"plays": [dict(r) for r in rows], "total": len(rows)}

@app.get("/v1/charts")
async def charts_data(
    mes:      str = "",
    fecha:    str = "",
    hasta:    str = "",
    id_local: str = "",
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    df = _build_date_filter(mes, fecha, hasta)
    lf = f"AND venue_id = '{id_local}'" if id_local else ""
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(f"""
            SELECT artista, isrc, COUNT(*) as plays
            FROM plays WHERE artista != '' {df} {lf}
            GROUP BY artista ORDER BY plays DESC LIMIT 50
        """).fetchall()
    return {"artistas": [{"artista": r["artista"], "isrc": r["isrc"], "plays": r["plays"]} for r in rows]}

def _build_artista_response(rows, venues_map: dict) -> dict:
    """Build the artista response format expected by the dashboard JS."""
    # Group by venue_id
    locales_map: dict = {}
    for r in rows:
        vid = r["venue_id"]
        if vid not in locales_map:
            v = venues_map.get(vid, {})
            locales_map[vid] = {
                "local_id":    vid,
                "local_nombre": v.get("nombre", vid),
                "ciudad":      v.get("ciudad", ""),
                "veces":       0,
                "completas":   0,
            }
        locales_map[vid]["veces"]    += r["plays"]
        locales_map[vid]["completas"] += r["completas"] or 0
    locales = sorted(locales_map.values(), key=lambda x: -x["veces"])
    total_plays    = sum(l["veces"]    for l in locales)
    total_completas = sum(l["completas"] for l in locales)
    return {
        "totales": {
            "total_plays":    total_plays,
            "total_completas": total_completas,
            "total_locales":  len(locales),
        },
        "locales": locales,
    }

@app.get("/dashboard/artista/buscar")
async def dashboard_artista_buscar(
    artista:  str = "",
    mes:      str = "",
    fecha:    str = "",
    hasta:    str = "",
    id_local: str = "",
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    df = _build_date_filter(mes, fecha, hasta)
    local_filter = f"AND venue_id = '{id_local}'" if id_local else ""
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(f"""
            SELECT artista, titulo, venue_id, isrc,
                   COUNT(*) as plays,
                   SUM(CASE WHEN promovida_id IS NOT NULL THEN 1 ELSE 0 END) as completas
            FROM plays WHERE LOWER(artista) LIKE LOWER(?) {df} {local_filter}
            GROUP BY artista, titulo, venue_id
            ORDER BY plays DESC LIMIT 100
        """, (f"%{artista}%",)).fetchall()
    with get_conn(VENUES_DB) as conn:
        venues_map = {r["id"]: dict(r) for r in conn.execute("SELECT id, nombre, ciudad FROM venues").fetchall()}
    result = _build_artista_response(rows, venues_map)
    result["artista"] = artista
    return result

@app.get("/dashboard/artista/{isrc}")
async def dashboard_artista(
    isrc:     str,
    mes:      str = "",
    fecha:    str = "",
    hasta:    str = "",
    id_local: str = "",
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    df = _build_date_filter(mes, fecha, hasta)
    local_filter = f"AND venue_id = '{id_local}'" if id_local else ""
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(f"""
            SELECT artista, titulo, venue_id, isrc,
                   COUNT(*) as plays,
                   SUM(CASE WHEN promovida_id IS NOT NULL THEN 1 ELSE 0 END) as completas
            FROM plays WHERE isrc=? {df} {local_filter}
            GROUP BY artista, titulo, venue_id
        """, (isrc,)).fetchall()
    with get_conn(VENUES_DB) as conn:
        venues_map = {r["id"]: dict(r) for r in conn.execute("SELECT id, nombre, ciudad FROM venues").fetchall()}
    result = _build_artista_response(rows, venues_map)
    result["isrc"] = isrc
    return result

@app.get("/dashboard/bar/{local_id}")
async def dashboard_bar(
    local_id: str,
    mes:      str = "",
    fecha:    str = "",
    hasta:    str = "",
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    df = _build_date_filter(mes, fecha, hasta)
    with get_conn(PLAYS_DB) as conn:
        stats = conn.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN promovida_id IS NOT NULL THEN 1 ELSE 0 END) as efectivos
            FROM plays WHERE venue_id=? {df}
        """, (local_id,)).fetchone()
        top = conn.execute(f"""
            SELECT artista, titulo, isrc,
                   COUNT(*) as plays,
                   AVG(porcentaje) as avg_pct,
                   SUM(CASE WHEN promovida_id IS NOT NULL THEN 1 ELSE 0 END) as completas,
                   GROUP_CONCAT(DISTINCT fuente) as fuente_raw
            FROM plays WHERE venue_id=? {df} AND artista != ''
            GROUP BY artista, titulo ORDER BY plays DESC LIMIT 20
        """, (local_id,)).fetchall()
    with get_conn(VENUES_DB) as conn:
        v = conn.execute("SELECT nombre, ciudad FROM venues WHERE id=?", (local_id,)).fetchone()
    total = stats["total"] or 0
    efectivos = stats["efectivos"] or 0
    canciones = []
    for r in top:
        fuente = (r["fuente_raw"] or "").split(",")[0]
        canciones.append({
            "artista":      r["artista"],
            "titulo":       r["titulo"],
            "isrc":         r["isrc"] or "",
            "veces":        r["plays"],
            "pct_promedio": round(r["avg_pct"] or 0, 1),
            "completas":    r["completas"] or 0,
            "fuente":       fuente,
        })
    return {
        "id_local": local_id,
        "nombre":   v["nombre"] if v else local_id,
        "ciudad":   v["ciudad"] if v else "",
        "resumen": {
            "total_plays": total,
            "plays_cpm":   efectivos,
        },
        "canciones": canciones,
        # legacy fields for backward compat
        "total_plays": total,
        "plays_cpm":   efectivos,
        "top_songs":   [{"artista": c["artista"], "titulo": c["titulo"],
                         "isrc": c["isrc"], "plays": c["veces"],
                         "avg_pct": c["pct_promedio"]} for c in canciones],
    }


# ── Catálogo CPM ───────────────────────────────────────────────────────────────

@app.get("/admin/catalogo")
async def admin_catalogo(x_session_token: str = Header(alias="X-Session-Token", default="")):
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute("""
            SELECT id, artista, titulo, isrc, genero, pvp, valor_establecimiento,
                   spotify_url, youtube_url, cdn_url, thumbnail_url, activo, created_at
            FROM catalogo_cpm ORDER BY artista, titulo
        """).fetchall()
    return [dict(r) for r in rows]

@app.get("/v1/catalogo")
async def public_catalogo(x_session_token: str = Header(alias="X-Session-Token", default="")):
    """Catálogo para el rol establecimiento (solo lectura)."""
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute("""
            SELECT id, artista, titulo, isrc, genero, valor_establecimiento,
                   spotify_url, youtube_url, activo
            FROM catalogo_cpm WHERE activo=1 ORDER BY artista, titulo
        """).fetchall()
    return [dict(r) for r in rows]

@app.post("/admin/catalogo", status_code=201)
async def admin_add_catalogo(body: dict):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("""
            INSERT INTO catalogo_cpm (artista, titulo, isrc, genero, pvp, valor_establecimiento,
                spotify_url, youtube_url, cdn_url, thumbnail_url, activo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (body.get("artista",""), body.get("titulo",""), body.get("isrc",""),
              body.get("genero",""), body.get("pvp", 3000), body.get("valor_establecimiento", 500),
              body.get("spotify_url",""), body.get("youtube_url",""),
              body.get("cdn_url",""), body.get("thumbnail_url",""),
              body.get("activo", 1)))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": new_id}

@app.put("/admin/catalogo/{song_id}")
async def admin_update_catalogo(song_id: int, body: dict):
    allowed = ["artista","titulo","isrc","genero","pvp","valor_establecimiento",
               "spotify_url","youtube_url","cdn_url","thumbnail_url","activo"]
    fields = [k for k in allowed if k in body]
    if fields:
        sql = f"UPDATE catalogo_cpm SET {', '.join(f+' =?' for f in fields)} WHERE id=?"
        vals = [body[f] for f in fields] + [song_id]
        with get_conn(PLAYS_DB) as conn:
            conn.execute(sql, vals)
    return {"ok": True}

@app.delete("/admin/catalogo/{song_id}")
async def admin_delete_catalogo(song_id: int):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("DELETE FROM catalogo_cpm WHERE id=?", (song_id,))
    return {"ok": True}

@app.post("/admin/catalogo/fingerprint")
async def upload_and_fingerprint(
    file:     UploadFile = File(...),
    artista:  str        = Form(""),
    titulo:   str        = Form(""),
    isrc:     str        = Form(""),
    genero:   str        = Form(""),
    spotify_url: str     = Form(""),
    youtube_url: str     = Form(""),
    x_session_token: str = Header(alias="X-Session-Token", default="")
):
    """
    Recibe un archivo MP3/MP4/WAV, corre fpcalc para generar el fingerprint,
    guarda la canción en catalogo_cpm Y en fingerprints.db para que la app
    la pueda identificar en venues.
    """
    FPCALC = shutil.which("fpcalc") or "/usr/bin/fpcalc"
    if not os.path.exists(FPCALC):
        raise HTTPException(status_code=503, detail="fpcalc no disponible en el servidor")

    # Guardar archivo temporal
    suffix = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()

        # Correr fpcalc
        result = subprocess.run(
            [FPCALC, "-json", tmp.name],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise HTTPException(status_code=422,
                detail=f"fpcalc error: {result.stderr.strip() or 'archivo no reconocido'}")

        fp_data    = json.loads(result.stdout)
        fingerprint = fp_data.get("fingerprint", "")
        duration    = float(fp_data.get("duration", 0))

        if not fingerprint:
            raise HTTPException(status_code=422, detail="No se pudo extraer fingerprint del archivo")

    finally:
        try: os.unlink(tmp.name)
        except Exception: pass

    artista_clean = artista.strip()
    titulo_clean  = titulo.strip()

    # 1) Guardar en catalogo_cpm
    with get_conn(PLAYS_DB) as conn:
        conn.execute("""
            INSERT INTO catalogo_cpm
            (artista, titulo, isrc, genero, spotify_url, youtube_url, activo)
            VALUES (?,?,?,?,?,?,1)
        """, (artista_clean, titulo_clean, isrc.strip(), genero.strip(),
              spotify_url.strip(), youtube_url.strip()))
        cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 2) Guardar en fingerprints.db para matching en venues
    fp_saved = False
    if os.path.exists(FINGERPRINTS_DB):
        try:
            with get_conn(FINGERPRINTS_DB) as conn:
                # Verificar si ya existe
                exists = conn.execute(
                    "SELECT id FROM tracks WHERE LOWER(artista_final)=LOWER(?) AND LOWER(titulo_final)=LOWER(?)",
                    (artista_clean, titulo_clean)
                ).fetchone()
                if not exists:
                    conn.execute("""
                        INSERT INTO tracks
                        (filepath, filename, extension, artista_final, titulo_final,
                         isrc, fingerprint, duration_seg, isrc_estado,
                         procesado, active, created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,1,1,datetime('now'),datetime('now'))
                    """, (
                        f"catalogo_cpm:{cat_id}",
                        f"{artista_clean} - {titulo_clean}",
                        suffix.lstrip("."),
                        artista_clean, titulo_clean,
                        isrc.strip(),
                        fingerprint,
                        duration,
                        "verificado" if isrc.strip() else "pendiente"
                    ))
                    fp_saved = True
                else:
                    # Actualizar fingerprint si ya existe pero no tenía
                    conn.execute("""
                        UPDATE tracks SET fingerprint=?, duration_seg=?, updated_at=datetime('now')
                        WHERE LOWER(artista_final)=LOWER(?) AND LOWER(titulo_final)=LOWER(?)
                          AND (fingerprint IS NULL OR fingerprint='')
                    """, (fingerprint, duration, artista_clean, titulo_clean))
                    fp_saved = True
        except Exception as e:
            log.error(f"[Upload] Error guardando en fingerprints.db: {e}")

    # 3) Recargar índice en background
    import threading
    def _reload_fp():
        load_fp_index()
        load_fp_index_promovidas()
    threading.Thread(target=_reload_fp, daemon=True).start()

    log.info(f"[Upload] ✅ '{artista_clean} - {titulo_clean}' · dur={duration:.1f}s · fp_saved={fp_saved}")
    return {
        "ok": True,
        "catalogo_id": cat_id,
        "artista":     artista_clean,
        "titulo":      titulo_clean,
        "duration":    round(duration, 1),
        "fingerprint_guardado": fp_saved,
        "mensaje": f"Canción agregada al catálogo{'  y al índice de fingerprints' if fp_saved else ''}."
    }

@app.post("/admin/upload")
async def admin_upload_stub():
    """Stub — carga a CDN no configurada en este servidor."""
    return {"error": "Upload CDN no configurado"}


# ── Configuración global de precios ───────────────────────────────────────────

def get_system_config(conn) -> dict:
    """Lee la config de precios del servidor."""
    rows = conn.execute("SELECT key, value FROM system_config").fetchall()
    cfg = {r[0]: r[1] for r in rows}
    return {
        "precio_por_play": float(cfg.get("precio_por_play", 4000)),
        "pct_estab":       float(cfg.get("pct_estab", 12.5)),
        "umbral_pct":      float(cfg.get("umbral_pct", 80)),
    }

@app.get("/admin/config")
async def admin_get_config():
    with get_conn(PLAYS_DB) as conn:
        return get_system_config(conn)

@app.put("/admin/config")
async def admin_set_config(body: dict):
    allowed = {"precio_por_play", "pct_estab", "umbral_pct"}
    with get_conn(PLAYS_DB) as conn:
        for k, v in body.items():
            if k in allowed:
                conn.execute("INSERT OR REPLACE INTO system_config (key,value) VALUES (?,?)",
                             (k, str(v)))
    return {"ok": True}


# ── Planes de promoción ────────────────────────────────────────────────────────

@app.get("/admin/planes")
async def admin_planes(x_session_token: str = Header(alias="X-Session-Token", default="")):
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(
            "SELECT id, nombre, color, precio_plan, precio_play, total_plays, dias_semana, activo FROM planes_promo ORDER BY precio_play DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try: d["dias_semana"] = json.loads(d["dias_semana"])
        except Exception: d["dias_semana"] = [0,1,2,3,4,5,6]
        # Calcular total_plays real = precio_plan / precio_play (no usar el valor almacenado)
        pp = d.get("precio_play") or 0
        if pp > 0:
            d["total_plays"] = int(d.get("precio_plan", 0) / pp)
        result.append(d)
    return result

@app.post("/admin/planes", status_code=201)
async def admin_create_plan(body: dict):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("""
            INSERT INTO planes_promo (nombre, color, precio_plan, precio_play, total_plays, dias_semana, activo)
            VALUES (?,?,?,?,?,?,?)
        """, (body.get("nombre","Plan"), body.get("color","#3D8EFF"),
              body.get("precio_plan", 0), body.get("precio_play", 500),
              body.get("total_plays", 100), json.dumps(body.get("dias_semana",[0,1,2,3,4,5,6])),
              body.get("activo", 1)))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": new_id, "nombre": body.get("nombre")}

@app.put("/admin/planes/{plan_id}")
async def admin_update_plan(plan_id: int, body: dict):
    allowed = ["nombre","color","precio_plan","precio_play","total_plays","activo"]
    fields = [k for k in allowed if k in body]
    updates = [f + "=?" for f in fields]
    values  = [body[f] for f in fields]
    if "dias_semana" in body:
        updates.append("dias_semana=?")
        values.append(json.dumps(body["dias_semana"]))
    if updates:
        values.append(plan_id)
        with get_conn(PLAYS_DB) as conn:
            conn.execute(f"UPDATE planes_promo SET {', '.join(updates)} WHERE id=?", values)
    return {"ok": True}

@app.delete("/admin/planes/{plan_id}")
async def admin_delete_plan(plan_id: int):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("DELETE FROM planes_promo WHERE id=?", (plan_id,))
    return {"ok": True}


# ── Promociones (canciones_promovidas en formato antiguo) ──────────────────────

@app.get("/admin/promociones")
async def admin_promociones(x_session_token: str = Header(alias="X-Session-Token", default="")):
    with get_conn(PLAYS_DB) as conn:
        cfg = get_system_config(conn)
        tarifa_default = round(cfg["precio_por_play"] * cfg["pct_estab"] / 100, 2)

        rows = conn.execute("""
            SELECT cp.rowid as id,
                   cp.id as uuid,
                   cp.artista_nombre as artista,
                   cp.titulo,
                   cp.isrc,
                   cp.creditos_total,
                   cp.creditos_usados  as plays_usados,
                   cp.tarifa_venue,
                   cp.fecha_inicio,
                   cp.fecha_fin,
                   cp.dias_semana,
                   cp.plan_id,
                   cp.activa,
                   cp.created_at,
                   pp.nombre     as plan_nombre,
                   pp.color      as plan_color,
                   pp.precio_plan as plan_precio_plan,
                   pp.precio_play as plan_precio_play
            FROM canciones_promovidas cp
            LEFT JOIN planes_promo pp ON pp.id = cp.plan_id
            ORDER BY cp.created_at DESC
        """).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        d["cancion_id"] = d["id"]
        try:
            d["dias_semana"] = json.loads(d["dias_semana"] or "[]")
        except Exception:
            d["dias_semana"] = [0,1,2,3,4,5,6]

        # total_plays: siempre calculado desde el plan si existe
        plan_pp = d.get("plan_precio_play") or 0
        plan_precio = d.get("plan_precio_plan") or 0
        if plan_pp > 0 and plan_precio > 0:
            d["total_plays"] = int(plan_precio / plan_pp)
        else:
            d["total_plays"] = d.get("creditos_total") or 0

        # tarifa_venue: usar config global por defecto
        d["precio_play"] = tarifa_default

        d["plays_restantes"] = max(0, d["total_plays"] - d["plays_usados"])

        # status
        if d["total_plays"] > 0 and d["plays_usados"] >= d["total_plays"]:
            d["status"] = "completada"
        elif d["activa"]:
            d["status"] = "activa"
        else:
            d["status"] = "pausada"
        result.append(d)
    return result

@app.post("/admin/promociones", status_code=201)
async def admin_create_promocion(body: dict, x_session_token: str = Header(alias="X-Session-Token", default="")):
    import uuid as _uuid
    promo_id = str(_uuid.uuid4())
    activa = 1 if body.get("status","activa") == "activa" else 0

    artista_nombre = body.get("artista_nombre") or body.get("artista", "")
    titulo         = body.get("titulo", "")
    isrc           = body.get("isrc", "")

    # Si viene cancion_id, buscar en catalogo_cpm
    if body.get("cancion_id") and (not titulo):
        with get_conn(PLAYS_DB) as conn:
            cat = conn.execute("SELECT artista, titulo, isrc FROM catalogo_cpm WHERE id=?",
                               (body["cancion_id"],)).fetchone()
            if cat:
                artista_nombre = artista_nombre or cat["artista"]
                titulo         = cat["titulo"]
                isrc           = isrc or cat["isrc"]

    with get_conn(PLAYS_DB) as conn:
        cfg = get_system_config(conn)
        tarifa_default = round(cfg["precio_por_play"] * cfg["pct_estab"] / 100, 2)

        # Calcular total_plays: desde el plan si hay plan_id, sino desde precio_plan/precio_play
        plan_id = body.get("plan_id")
        if plan_id:
            plan = conn.execute(
                "SELECT precio_plan, precio_play FROM planes_promo WHERE id=?", (plan_id,)
            ).fetchone()
            if plan and plan[1] > 0:
                total_plays = int(plan[0] / plan[1])
            else:
                total_plays = body.get("total_plays") or 100
        else:
            precio_plan = body.get("precio_plan", 0)
            precio_play_plan = body.get("precio_play", 0)
            total_plays = body.get("total_plays") or (
                int(precio_plan / precio_play_plan) if precio_plan and precio_play_plan else 100
            )

        # tarifa_venue: usar la del body solo si viene explícita y diferente al default
        tarifa_venue = body.get("tarifa_venue", tarifa_default) or tarifa_default
        conn.execute("""
            INSERT INTO canciones_promovidas
            (id, artista_id, artista_nombre, titulo, isrc, genero,
             creditos_total, tarifa_venue, fecha_inicio, fecha_fin,
             dias_semana, plan_id, activa)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (promo_id, body.get("artista_id",""), artista_nombre, titulo, isrc, "",
              total_plays, tarifa_venue,
              body.get("fecha_inicio",""), body.get("fecha_fin") or "",
              json.dumps(body.get("dias_semana",[0,1,2,3,4,5,6])),
              body.get("plan_id"), activa))
        rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": rowid, "uuid": promo_id}

@app.put("/admin/promociones/{promo_rowid}")
async def admin_update_promocion(promo_rowid: int, body: dict):
    field_map = {
        "total_plays":  "creditos_total",
        "precio_play":  "tarifa_venue",
        "fecha_inicio": "fecha_inicio",
        "fecha_fin":    "fecha_fin",
        "plan_id":      "plan_id",
        "titulo":       "titulo",
        "artista":      "artista_nombre",
        "isrc":         "isrc",
    }
    updates = []
    values  = []
    for key, col in field_map.items():
        if key in body:
            updates.append(f"{col}=?")
            values.append(body[key])
    if "status" in body:
        updates.append("activa=?")
        values.append(1 if body["status"] == "activa" else 0)
    if "dias_semana" in body:
        updates.append("dias_semana=?")
        values.append(json.dumps(body["dias_semana"]))
    if updates:
        values.append(promo_rowid)
        with get_conn(PLAYS_DB) as conn:
            conn.execute(f"UPDATE canciones_promovidas SET {', '.join(updates)} WHERE rowid=?", values)
    return {"ok": True}

@app.delete("/admin/promociones/{promo_rowid}")
async def admin_delete_promocion(promo_rowid: int):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("DELETE FROM canciones_promovidas WHERE rowid=?", (promo_rowid,))
    return {"ok": True}


# ── Mensajes ───────────────────────────────────────────────────────────────────

@app.get("/admin/mensajes")
async def admin_mensajes(x_session_token: str = Header(alias="X-Session-Token", default="")):
    with get_conn(PLAYS_DB) as conn:
        rows = conn.execute(
            "SELECT id, titulo, imagen_url, boton_texto, boton_url, activo, created_at FROM mensajes ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

@app.post("/admin/mensajes", status_code=201)
async def admin_create_mensaje(body: dict):
    with get_conn(PLAYS_DB) as conn:
        conn.execute(
            "INSERT INTO mensajes (titulo, imagen_url, boton_texto, boton_url) VALUES (?,?,?,?)",
            (body.get("titulo",""), body.get("imagen_url",""),
             body.get("boton_texto",""), body.get("boton_url",""))
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": new_id}

@app.delete("/admin/mensajes/{msg_id}")
async def admin_delete_mensaje(msg_id: int):
    with get_conn(PLAYS_DB) as conn:
        conn.execute("DELETE FROM mensajes WHERE id=?", (msg_id,))
    return {"ok": True}


# ── Bulk-batch stubs (carga masiva) ────────────────────────────────────────────

@app.get("/admin/bulk-batches")
async def bulk_batches_list():
    return []

@app.post("/admin/bulk-batch")
async def bulk_batch_create():
    return {"error": "No implementado — usa el panel de catálogo"}

@app.get("/admin/bulk-batch/{bid}")
async def bulk_batch_get(bid: str):
    raise HTTPException(status_code=404, detail="Batch no encontrado")

@app.delete("/admin/bulk-batch/{bid}")
async def bulk_batch_delete(bid: str):
    return {"ok": True}

@app.post("/admin/bulk-batch/{bid}/lock")
async def bulk_batch_lock(bid: str):
    return {"ok": True}

@app.post("/admin/bulk-batch/{bid}/unlock")
async def bulk_batch_unlock(bid: str):
    return {"ok": True}

@app.post("/admin/bulk-batch/{bid}/aprobar")
async def bulk_batch_aprobar(bid: str):
    return {"ok": True}

@app.put("/admin/bulk-batch/{bid}/item/{iid}")
async def bulk_batch_item_update(bid: str, iid: str, body: dict):
    return {"ok": True}


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # Inicializar bases de datos
    init_plays_db()
    init_venues_db()

    port = int(os.getenv("PORT", "8000"))
    log.info(f"🎵 SumarteRed Monitor Server v3.0 — escuchando en http://0.0.0.0:{port}")
    log.info(f"   fingerprints.db: {FINGERPRINTS_DB}")
    log.info(f"   ACOUSTID_API_KEY: {'✅ configurada' if ACOUSTID_API_KEY else '❌ NO configurada'}")
    log.info(f"   Score threshold: {SCORE_THRESHOLD}")

    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
