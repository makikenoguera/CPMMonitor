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
import json
import sqlite3
import hashlib
import asyncio
import logging
import base64
import struct
from typing import Optional
from datetime import datetime, timezone

import ssl
import certifi
import aiohttp
import numpy as np

# Chromaprint: decodificación nativa vía pyacoustid (acoustid.chromaprint)
try:
    from acoustid import chromaprint as _cp
    _CHROMAPRINT_OK = True
except Exception:
    _CHROMAPRINT_OK = False
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sumartered")

app = FastAPI(title="SumarteRed Monitor", version="3.0.0")


@app.on_event("startup")
async def startup():
    """Inicializa las bases de datos al arrancar (funciona con uvicorn directo o gunicorn)."""
    init_plays_db()
    init_venues_db()
    load_fp_index()   # carga fingerprints en memoria para matching local


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuración ──────────────────────────────────────────────────────────────
ACOUSTID_API_KEY = os.getenv("ACOUSTID_API_KEY", "")   # API key del servidor para AcousticID
FINGERPRINTS_DB  = os.getenv("FINGERPRINTS_DB",  "fingerprints.db")   # catálogo SumarteRed
PLAYS_DB         = os.getenv("PLAYS_DB",         "plays.db")          # plays registrados
VENUES_DB        = os.getenv("VENUES_DB",         "venues.db")         # venues registrados
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
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_plays_venue_id   ON plays(venue_id);
        CREATE INDEX IF NOT EXISTS idx_plays_created_at ON plays(created_at);
        CREATE INDEX IF NOT EXISTS idx_plays_isrc       ON plays(isrc);
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


def _decode_chromaprint(fp_str: str) -> Optional[np.ndarray]:
    """
    Decodifica un fingerprint Chromaprint en cualquier formato → numpy array int32.

    Formatos soportados:
    A) Base64url estándar (fpcalc sin -raw)   → decodificado con libchromaprint nativa
    B) Enteros separados por coma (fpcalc -raw) → parseados directamente como uint32
    C) Fallback raw bytes si la librería nativa falla

    El formato B resulta de usar fpcalc con el flag -raw, que emite valores uint32
    sin comprimir en lugar del string base64url comprimido con Golomb-Rice.
    """
    if not fp_str:
        return None

    # Detectar formato B: enteros separados por coma (fpcalc -raw)
    # Ejemplo: "2721074174,2725711326,2725646734,..."
    if "," in fp_str:
        try:
            vals = [int(v.strip()) for v in fp_str.split(",") if v.strip()]
            if len(vals) >= 10:
                arr = np.array(vals, dtype=np.uint32).view(np.int32)
                log.debug(f"[FP] formato raw-int32 ({len(arr)} valores)")
                return arr
        except Exception as e:
            log.warning(f"[FP] fallo parseando formato raw-int32: {e!r}")
        return None

    # Formato A: base64url → decodificación nativa con libchromaprint
    if _CHROMAPRINT_OK:
        try:
            raw, _algo = _cp.decode_fingerprint(fp_str.encode(), base64=True)
            arr = np.array(raw, dtype=np.uint32).view(np.int32)
            if len(arr) >= 10:
                return arr
        except Exception as e:
            log.warning(f"[FP] native decode failed fp_len={len(fp_str)} err={e!r}")

    # Formato C: fallback manual (bytes crudos tras cabecera de 4 bytes)
    try:
        s = fp_str.replace("-", "+").replace("_", "/")
        s += "=" * (-len(s) % 4)
        data = base64.b64decode(s)
        payload = data[4:] if len(data) > 4 else data
        n = len(payload) // 4
        if n < 10:
            return None
        return np.frombuffer(payload[: n * 4], dtype="<u4").view(np.int32)
    except Exception:
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


def load_fp_index():
    """Carga todos los fingerprints procesados de fingerprints.db en memoria."""
    global _fp_index
    if not os.path.exists(FINGERPRINTS_DB):
        log.warning("[FP Index] fingerprints.db no encontrada — búsqueda local deshabilitada")
        return

    try:
        with get_conn(FINGERPRINTS_DB) as conn:
            rows = conn.execute(
                """SELECT artista_final, titulo_final, isrc, duration_seg, fingerprint
                   FROM tracks
                   WHERE procesado = 1 AND fingerprint IS NOT NULL"""
            ).fetchall()

        index = []
        skipped = 0
        for i, row in enumerate(rows):
            arr = _decode_chromaprint(row["fingerprint"])
            if arr is None or len(arr) < 20:
                skipped += 1
                continue
            index.append({
                "artista":  row["artista_final"] or "",
                "titulo":   row["titulo_final"]  or "",
                "isrc":     row["isrc"]          or "",
                "duration": row["duration_seg"]  or 0,
                "fp":       arr,
            })

        _fp_index = index
        log.info(f"[FP Index] {len(index)} tracks cargados ({skipped} omitidos)")
    except Exception as e:
        log.error(f"[FP Index] Error cargando índice: {e}")


def search_by_fingerprint(query_fp: str, threshold: float = 0.70) -> Optional[dict]:
    """
    Busca en el índice local de fingerprints.
    Retorna el track con mayor similaridad si supera `threshold`.

    Threshold 0.70: empírico para Chromaprint de 10s vs canción completa.
    - <0.50  → azar (flip de moneda para bits binarios)
    - 0.55   → umbral anterior, generaba muchos falsos positivos
    - 0.70   → mínimo para considerar un match confiable en clips cortos
    - >0.85  → match casi seguro
    """
    if not _fp_index:
        return None

    query_arr = _decode_chromaprint(query_fp)
    if query_arr is None or len(query_arr) < 10:
        return None

    best_score  = 0.0
    best_track  = None

    for entry in _fp_index:
        score = _sliding_score(query_arr, entry["fp"])
        if score > best_score:
            best_score = score
            best_track = entry
            if best_score > 0.90:
                break

    if best_score >= threshold and best_track:
        log.info(
            f"[LocalMatch] ✅ {best_track['artista']} - {best_track['titulo']} "
            f"(score={best_score:.2f})"
        )
        return {**best_track, "confianza": best_score}

    log.info(f"[LocalMatch] Sin match local (mejor score={best_score:.2f})")
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
        for play in payload.plays:
            try:
                conn.execute("""
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
                accepted.append(play.idempotency_key)
            except Exception as e:
                log.error(f"[Plays] Error insertando play {play.idempotency_key}: {e}")

    log.info(f"[Plays] Recibidos: {len(accepted)}/{len(payload.plays)} para venue {first.venue_id}")
    return {"accepted": accepted, "total": len(accepted)}


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

@app.get("/admin/stats")
async def get_stats():
    """Estadísticas globales del sistema."""
    with get_conn(PLAYS_DB) as conn:
        total = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
        in_catalog = conn.execute("SELECT COUNT(*) FROM plays WHERE in_catalog=1").fetchone()[0]
        with_isrc = conn.execute("SELECT COUNT(*) FROM plays WHERE isrc != ''").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM plays WHERE DATE(created_at)=DATE('now')"
        ).fetchone()[0]

    return {
        "total_plays":      total,
        "in_catalog":       in_catalog,
        "with_isrc":        with_isrc,
        "today":            today,
        "catalog_rate":     round(in_catalog / total * 100, 1) if total > 0 else 0,
    }


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
