#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  CPM Fingerprint Builder                                     ║
║  Sumarte Red — procesamiento masivo de huellas acústicas     ║
╠══════════════════════════════════════════════════════════════╣
║  Qué hace:                                                   ║
║  1. Escanea un directorio en busca de archivos de audio      ║
║  2. Genera fingerprint con fpcalc (Chromaprint)              ║
║  3. Consulta AcousticID → obtiene ISRC + metadata            ║
║  4. Si no hay ISRC en AcousticID → busca en MusicBrainz      ║
║  5. Guarda todo en fingerprints.db (SQLite local)            ║
║  6. Es reanudable: nunca reprocesa lo ya procesado           ║
╠══════════════════════════════════════════════════════════════╣
║  Uso:                                                        ║
║    python3 build_fingerprints.py /ruta/mp3s                  ║
║    python3 build_fingerprints.py /ruta/mp3s --batch 500      ║
║    python3 build_fingerprints.py --stats                     ║
║    python3 build_fingerprints.py --exportar                  ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, sqlite3, subprocess, argparse, re
import urllib.request, urllib.parse, urllib.error, ssl
from pathlib import Path
from datetime import datetime

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    import mutagen.mp3, mutagen.id3, mutagen.flac, mutagen.mp4
    MUTAGEN = True
except ImportError:
    MUTAGEN = False

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

# ─── Configuración ────────────────────────────────────────────────────────
ACOUSTID_KEY       = "x4W6Y5Mxjx"
ACOUSTID_URL       = "https://api.acoustid.org/v2/lookup"
MB_URL             = "https://musicbrainz.org/ws/2/recording/"
MB_USER_AGENT      = "CPMFingerprintBuilder/1.0 (monitor@cpmtracks.com)"
ACOUSTID_MIN_SCORE = 0.75   # score mínimo para aceptar resultado de AcousticID
DELAY_ACOUSTID     = 0.35   # segundos entre llamadas (máx 3/segundo)
DELAY_MB           = 1.1    # segundos entre llamadas MusicBrainz (máx 1/segundo)
AUDIO_EXTENSIONS   = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".wma"}
DB_PATH            = Path(__file__).parent / "fingerprints.db"

# ─── Localizar fpcalc ─────────────────────────────────────────────────────
def find_fpcalc():
    candidates = [
        "/opt/homebrew/bin/fpcalc",
        "/usr/local/bin/fpcalc",
        "/usr/bin/fpcalc",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    try:
        r = subprocess.run(["which", "fpcalc"], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None

FPCALC = find_fpcalc()

# ─── Base de datos ────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tracks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        filepath        TEXT    UNIQUE NOT NULL,
        filename        TEXT    NOT NULL,
        extension       TEXT,
        artista_tag     TEXT,
        titulo_tag      TEXT,
        artista_final   TEXT,
        titulo_final    TEXT,
        fingerprint     TEXT,
        duration_seg    REAL,
        mbid            TEXT,
        isrc            TEXT,
        isrc_fuente     TEXT,
        isrc_estado     TEXT    NOT NULL DEFAULT 'pendiente',
        afiliado        INTEGER NOT NULL DEFAULT 0,
        acoustid_score  REAL,
        procesado       INTEGER NOT NULL DEFAULT 0,
        error           TEXT,
        created_at      REAL    NOT NULL,
        updated_at      REAL
    );
    CREATE INDEX IF NOT EXISTS idx_procesado  ON tracks(procesado);
    CREATE INDEX IF NOT EXISTS idx_isrc       ON tracks(isrc);
    CREATE INDEX IF NOT EXISTS idx_artista    ON tracks(artista_final);
    CREATE INDEX IF NOT EXISTS idx_estado     ON tracks(isrc_estado);
    """)
    conn.commit()
    return conn

# ─── Leer metadatos del archivo ───────────────────────────────────────────
def read_tags(filepath):
    """Lee artista y título de los metadatos del archivo.
    Fallback: intenta parsear 'Artista - Titulo' del nombre del archivo."""
    artista, titulo = "", ""

    if MUTAGEN:
        try:
            path = str(filepath)
            ext  = Path(path).suffix.lower()

            if ext == ".mp3":
                audio = mutagen.mp3.MP3(path)
                tags  = audio.tags
                if tags:
                    artista = str(tags.get("TPE1", [""])[0]).strip()
                    titulo  = str(tags.get("TIT2", [""])[0]).strip()

            elif ext == ".flac":
                audio = mutagen.flac.FLAC(path)
                artista = (audio.get("artist",  [""])[0]).strip()
                titulo  = (audio.get("title",   [""])[0]).strip()

            elif ext in (".m4a", ".aac"):
                audio = mutagen.mp4.MP4(path)
                artista = str(audio.tags.get("\xa9ART", [""])[0]).strip() if audio.tags else ""
                titulo  = str(audio.tags.get("\xa9nam", [""])[0]).strip() if audio.tags else ""
        except Exception:
            pass

    # Fallback: nombre del archivo
    if not titulo:
        stem = Path(filepath).stem
        # Quitar número de pista al inicio: "01 - Titulo" o "01. Titulo"
        stem = re.sub(r"^\d+[\s\.\-]+", "", stem)
        if " - " in stem:
            parts   = stem.split(" - ", 1)
            artista = artista or parts[0].strip()
            titulo  = parts[1].strip()
        else:
            titulo  = stem.strip()

    return artista, titulo

# ─── Generar fingerprint ──────────────────────────────────────────────────
def generate_fingerprint(filepath):
    """Ejecuta fpcalc -json y devuelve (fingerprint, duration_seg) o (None, None)."""
    if not FPCALC:
        return None, None
    try:
        result = subprocess.run(
            [FPCALC, "-json", str(filepath)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return None, None
        data = json.loads(result.stdout)
        fp   = data.get("fingerprint")
        dur  = data.get("duration")
        return fp, float(dur) if dur else None
    except Exception:
        return None, None

# ─── HTTP helper ──────────────────────────────────────────────────────────
def http_post(url, params_dict, timeout=20):
    data = urllib.parse.urlencode(params_dict).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "User-Agent":    MB_USER_AGENT,
            "Content-Type":  "application/x-www-form-urlencoded",
        }
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=timeout) as r:
        return json.loads(r.read())

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": MB_USER_AGENT})
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=timeout) as r:
        return json.loads(r.read())

# ─── AcousticID ───────────────────────────────────────────────────────────
def query_acoustid(fingerprint, duration):
    """
    Consulta AcousticID con el fingerprint (POST).
    Devuelve dict con: mbid, isrc, artista, titulo, score
    Todos pueden ser None si no se encuentra.
    """
    try:
        data = http_post(ACOUSTID_URL, {
            "client":      ACOUSTID_KEY,
            "duration":    int(duration),
            "fingerprint": fingerprint,
            "meta":        "recordings+isrcs",
        })
    except Exception as e:
        return {"error": str(e)}

    if data.get("status") != "ok" or not data.get("results"):
        return {}

    best = {}
    best_score = 0.0

    for result in data["results"]:
        score = float(result.get("score", 0))
        if score < ACOUSTID_MIN_SCORE:
            continue

        for rec in result.get("recordings", []):
            isrcs   = rec.get("isrcs", [])
            mbid    = rec.get("id", "")
            titulo  = rec.get("title", "")
            artists = rec.get("artists", [])
            artista = artists[0]["name"] if artists else ""

            # Prioridad: score alto + tiene ISRC
            tiene_isrc = bool(isrcs)
            score_ef   = score + (0.05 if tiene_isrc else 0)

            if score_ef > best_score and mbid:
                best_score = score_ef
                best = {
                    "mbid":    mbid,
                    "isrc":    isrcs[0] if isrcs else None,
                    "artista": artista,
                    "titulo":  titulo,
                    "score":   score,
                }

    return best

# ─── MusicBrainz ──────────────────────────────────────────────────────────
def query_musicbrainz_by_mbid(mbid):
    """Dado un MBID, obtiene los ISRCs asociados desde MusicBrainz."""
    try:
        url  = f"{MB_URL}{mbid}?inc=isrcs&fmt=json"
        data = http_get(url)
        isrcs = data.get("isrcs", [])
        return isrcs[0] if isrcs else None
    except Exception:
        return None

def query_musicbrainz_by_text(artista, titulo):
    """Busca por texto artista+título en MusicBrainz.
    Devuelve (mbid, isrc) o (None, None)."""
    if not artista and not titulo:
        return None, None
    try:
        parts = []
        if titulo:
            parts.append(f'recording:"{titulo}"')
        if artista:
            parts.append(f'artist:"{artista}"')
        params = urllib.parse.urlencode({
            "query": " AND ".join(parts),
            "fmt":   "json",
            "limit": "5",
            "inc":   "isrcs",
        })
        data = http_get(f"{MB_URL}?{params}")
        for rec in data.get("recordings", []):
            mbid  = rec.get("id")
            isrcs = rec.get("isrcs", [])
            if mbid and isrcs:
                return mbid, isrcs[0]
            if mbid:
                return mbid, None
    except Exception:
        pass
    return None, None

# ─── Registrar archivos en la BD ──────────────────────────────────────────
def register_files(conn, directory):
    """Escanea el directorio recursivamente y registra archivos de audio nuevos."""
    directory = Path(directory)
    if not directory.exists():
        print(f"❌ El directorio no existe: {directory}")
        sys.exit(1)

    archivos = [
        p for p in directory.rglob("*")
        if p.suffix.lower() in AUDIO_EXTENSIONS and p.is_file()
    ]

    nuevos, ya_existian = 0, 0
    now = time.time()

    for path in archivos:
        filepath = str(path.resolve())
        if conn.execute("SELECT id FROM tracks WHERE filepath=?", (filepath,)).fetchone():
            ya_existian += 1
            continue
        artista, titulo = read_tags(path)
        conn.execute(
            """INSERT INTO tracks
               (filepath, filename, extension, artista_tag, titulo_tag, created_at)
               VALUES (?,?,?,?,?,?)""",
            (filepath, path.name, path.suffix.lower(), artista, titulo, now)
        )
        nuevos += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    print(f"  📁 {total:,} tracks en BD  ({nuevos:,} nuevos  ·  {ya_existian:,} ya existían)")
    return total

# ─── Procesar un batch ────────────────────────────────────────────────────
def process_batch(conn, batch_size=100,
                  delay_acoustid=DELAY_ACOUSTID, delay_mb=DELAY_MB):

    if not FPCALC:
        print("❌ fpcalc no encontrado.")
        print("   Instalar: brew install chromaprint")
        sys.exit(1)

    pendientes = conn.execute(
        """SELECT id, filepath, filename, artista_tag, titulo_tag
           FROM tracks WHERE procesado=0
           ORDER BY id ASC LIMIT ?""",
        (batch_size,)
    ).fetchall()

    total_pendientes = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE procesado=0"
    ).fetchone()[0]

    if not pendientes:
        print("✅ No hay tracks pendientes de procesar.")
        return 0

    n          = len(pendientes)
    ok_acid    = 0   # ISRC via AcousticID
    ok_mb      = 0   # ISRC via MusicBrainz
    sin_isrc   = 0   # identificado pero sin ISRC
    no_id      = 0   # no reconocido por nadie
    errores    = 0   # fpcalc falló o archivo no existe

    print(f"\n🎵 Procesando {n:,} de {total_pendientes:,} pendientes...\n")
    t_inicio = time.time()

    for i, row in enumerate(pendientes, 1):
        track_id = row["id"]
        filepath = row["filepath"]
        filename = row["filename"]
        artista  = row["artista_tag"] or ""
        titulo   = row["titulo_tag"]  or ""

        label = filename[:55].ljust(55)
        print(f"  [{i:>4}/{n}] {label}", end="", flush=True)

        # ── Verificar que el archivo existe ──
        if not os.path.exists(filepath):
            _mark_error(conn, track_id, "archivo no encontrado")
            print(" ⚠️  no encontrado")
            errores += 1
            continue

        # ── Paso 1: Fingerprint ──
        fingerprint, duration = generate_fingerprint(filepath)
        if not fingerprint or not duration:
            _mark_error(conn, track_id, "fpcalc falló")
            print(" ❌ fpcalc falló")
            errores += 1
            continue

        # ── Paso 2: AcousticID ──
        time.sleep(delay_acoustid)
        acr = query_acoustid(fingerprint, duration)

        if "error" in acr:
            _mark_error(conn, track_id, f"AcousticID error: {acr['error']}")
            print(f" ⚠️  red: {acr['error'][:40]}")
            errores += 1
            continue

        artista_final = acr.get("artista") or artista
        titulo_final  = acr.get("titulo")  or titulo
        mbid          = acr.get("mbid")
        isrc          = acr.get("isrc")
        score         = acr.get("score", 0.0)

        # Si AcousticID devolvió MBID pero sin ISRC → buscar ISRC en MusicBrainz
        if mbid and not isrc:
            time.sleep(delay_mb)
            mb_isrc = query_musicbrainz_by_mbid(mbid)
            if mb_isrc:
                isrc = mb_isrc

        if isrc:
            _save_result(conn, track_id,
                         fingerprint, duration, mbid, isrc,
                         artista_final, titulo_final,
                         "acoustid" if acr.get("isrc") else "acoustid+mb",
                         score)
            print(f" ✅ {isrc}  [{score:.0%}]  {artista_final[:25]}")
            ok_acid += 1
            continue

        # ── Paso 3: MusicBrainz por texto (fallback) ──
        if artista_final or titulo_final:
            time.sleep(delay_mb)
            mb_mbid, mb_isrc = query_musicbrainz_by_text(artista_final, titulo_final)
            if mb_isrc:
                _save_result(conn, track_id,
                             fingerprint, duration, mb_mbid, mb_isrc,
                             artista_final, titulo_final,
                             "musicbrainz", score)
                print(f" 🔍 {mb_isrc}  (MusicBrainz texto)")
                ok_mb += 1
                continue
            mb_fallback = mb_mbid if (mb_mbid and not mbid) else None
        else:
            mb_fallback = None

        # ── Sin ISRC — guardar lo que tenemos ──
        if mbid or mb_fallback or artista_final or titulo_final:
            if mbid:
                fuente = "acoustid_sin_isrc"
            elif mb_fallback:
                fuente = "mb_sin_isrc"
                mbid   = mb_fallback
            else:
                fuente = "sin_match"
            _save_result(conn, track_id,
                         fingerprint, duration, mbid, None,
                         artista_final, titulo_final,
                         fuente, score)
            print(f" ⏳ sin ISRC  ({fuente}  {score:.0%})")
            sin_isrc += 1
        else:
            _save_result(conn, track_id,
                         fingerprint, duration, None, None,
                         artista_final, titulo_final,
                         "no_reconocido", 0.0)
            print(f" ❓ no reconocido")
            no_id += 1

    elapsed = time.time() - t_inicio
    total_restantes = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE procesado=0"
    ).fetchone()[0]

    print(f"""
┌───────────────────────────────────────────────────┐
│  Batch completado  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}        │
├───────────────────────────────────────────────────┤
│  ✅ ISRC via AcousticID       {ok_acid:>6,}              │
│  🔍 ISRC via MusicBrainz      {ok_mb:>6,}              │
│  ⏳ Identificado sin ISRC     {sin_isrc:>6,}              │
│  ❓ No reconocido             {no_id:>6,}              │
│  ❌ Errores                   {errores:>6,}              │
│  ─────────────────────────────────────────────    │
│  Procesados este batch        {n:>6,}              │
│  Tiempo                       {elapsed:>5.0f}s              │
│  Quedan pendientes            {total_restantes:>6,}              │
└───────────────────────────────────────────────────┘""")
    return n

# ─── Helpers internos ─────────────────────────────────────────────────────
def _mark_error(conn, track_id, msg):
    conn.execute(
        "UPDATE tracks SET procesado=1, error=?, updated_at=? WHERE id=?",
        (msg, time.time(), track_id)
    )
    conn.commit()

def _save_result(conn, track_id, fingerprint, duration, mbid, isrc,
                 artista, titulo, fuente, score):
    estado = "verificado" if isrc else "pendiente"
    conn.execute("""
        UPDATE tracks SET
            fingerprint=?, duration_seg=?, mbid=?, isrc=?,
            artista_final=?, titulo_final=?,
            isrc_fuente=?, isrc_estado=?,
            acoustid_score=?, procesado=1, error=NULL, updated_at=?
        WHERE id=?""",
        (fingerprint, duration, mbid, isrc,
         artista, titulo, fuente, estado,
         score, time.time(), track_id)
    )
    conn.commit()

# ─── Estadísticas ────────────────────────────────────────────────────────
def print_stats(conn):
    total       = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    procesados  = conn.execute("SELECT COUNT(*) FROM tracks WHERE procesado=1").fetchone()[0]
    pendientes  = total - procesados
    con_isrc    = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE isrc IS NOT NULL AND isrc!=''").fetchone()[0]
    sin_isrc    = procesados - con_isrc
    de_acid     = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE isrc_fuente LIKE 'acoustid%' AND isrc IS NOT NULL AND isrc!=''").fetchone()[0]
    de_mb       = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE isrc_fuente IN ('musicbrainz','acoustid+mb') AND isrc IS NOT NULL AND isrc!=''").fetchone()[0]
    errores     = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE error IS NOT NULL").fetchone()[0]
    pct_done    = (procesados/total*100) if total else 0
    pct_isrc    = (con_isrc/procesados*100) if procesados else 0

    print(f"""
╔═════════════════════════════════════════════════════╗
║  CPM Fingerprint Builder — Estado actual            ║
╠═════════════════════════════════════════════════════╣
║  Total tracks registrados    {total:>8,}               ║
║  ✅ Procesados               {procesados:>8,}  ({pct_done:.0f}%)        ║
║  ⏳ Pendientes               {pendientes:>8,}               ║
╠═════════════════════════════════════════════════════╣
║  Con ISRC verificado         {con_isrc:>8,}  ({pct_isrc:.0f}% de proc.) ║
║    → via AcousticID          {de_acid:>8,}               ║
║    → via MusicBrainz         {de_mb:>8,}               ║
║  Sin ISRC (pendiente manual) {sin_isrc:>8,}               ║
║  Errores (archivo/red)       {errores:>8,}               ║
╚═════════════════════════════════════════════════════╝
  DB: {DB_PATH}""")

# ─── Exportar a CSV ───────────────────────────────────────────────────────
def exportar_csv(conn):
    import csv
    out = Path(__file__).parent / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    rows = conn.execute("""
        SELECT filename, artista_final, titulo_final, isrc, isrc_fuente,
               isrc_estado, duration_seg, acoustid_score, afiliado, mbid
        FROM tracks ORDER BY artista_final, titulo_final
    """).fetchall()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo","artista","titulo","isrc","fuente_isrc",
                    "estado","duracion_seg","score_acoustid","afiliado","mbid"])
        for r in rows:
            w.writerow(list(r))
    print(f"✅ Exportado: {out}  ({len(rows):,} filas)")

# ─── Main ─────────────────────────────────────────────────────────────────
def main():
    # Defaults capturados antes del parsing
    _key   = ACOUSTID_KEY
    _score = ACOUSTID_MIN_SCORE
    _db    = str(DB_PATH)
    _dad   = DELAY_ACOUSTID
    _dmb   = DELAY_MB

    parser = argparse.ArgumentParser(
        description="CPM Fingerprint Builder — genera huellas acústicas y resuelve ISRCs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python3 build_fingerprints.py /Volumes/Music/tracks           # escanear + procesar 100
  python3 build_fingerprints.py /Volumes/Music/tracks --batch 500
  python3 build_fingerprints.py --batch 1000                    # procesar sin re-escanear
  python3 build_fingerprints.py --stats                         # solo ver estado
  python3 build_fingerprints.py --exportar                      # exportar CSV
  python3 build_fingerprints.py --reintento                     # reintentar los que fallaron
        """
    )
    parser.add_argument("directorio", nargs="?",
                        help="Directorio con los archivos de audio")
    parser.add_argument("--batch",     type=int,   default=100,
                        help="Tracks a procesar en este lote (default: 100)")
    parser.add_argument("--delay",     type=float, default=_dad,
                        help=f"Segundos entre llamadas AcousticID (default: {_dad})")
    parser.add_argument("--delay-mb",  type=float, default=_dmb,
                        help=f"Segundos entre llamadas MusicBrainz (default: {_dmb})")
    parser.add_argument("--key",       default=_key,
                        help="API key de AcousticID")
    parser.add_argument("--score",     type=float, default=_score,
                        help=f"Score mínimo AcousticID para aceptar (default: {_score})")
    parser.add_argument("--stats",     action="store_true",
                        help="Mostrar estadísticas y salir")
    parser.add_argument("--exportar",  action="store_true",
                        help="Exportar resultados a CSV y salir")
    parser.add_argument("--reintento", action="store_true",
                        help="Reintentar tracks que fallaron (error no-nulo)")
    parser.add_argument("--db",        default=_db,
                        help=f"Ruta de la base de datos (default: {_db})")

    args = parser.parse_args()

    # Aplicar overrides al módulo
    import sys as _sys
    _mod = _sys.modules[__name__]
    _mod.ACOUSTID_KEY       = args.key
    _mod.ACOUSTID_MIN_SCORE = args.score
    db_path = Path(args.db)
    _mod.DB_PATH            = db_path

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  CPM Fingerprint Builder — Sumarte Red                       ║
╠══════════════════════════════════════════════════════════════╣
║  fpcalc : {(FPCALC or '❌ NO ENCONTRADO — brew install chromaprint'):<50}║
║  mutagen: {'✅ instalado' if MUTAGEN else '⚠️  no instalado (pip3 install mutagen)':<50}║
║  BD     : {str(DB_PATH):<50}║
╚══════════════════════════════════════════════════════════════╝""")

    if not FPCALC and not args.stats and not args.exportar:
        print("\n❌ fpcalc es necesario para generar fingerprints.")
        print("   Instalar: brew install chromaprint")
        sys.exit(1)

    conn = init_db()

    if args.stats:
        print_stats(conn)
        return

    if args.exportar:
        exportar_csv(conn)
        return

    if args.reintento:
        print("🔄 Marcando tracks con error como pendientes...")
        n = conn.execute(
            "UPDATE tracks SET procesado=0, error=NULL WHERE error IS NOT NULL"
        ).rowcount
        conn.commit()
        print(f"   {n:,} tracks marcados para reintento")

    if args.directorio:
        print(f"\n📂 Escaneando: {args.directorio}")
        register_files(conn, args.directorio)

    print_stats(conn)
    process_batch(conn,
                  batch_size=args.batch,
                  delay_acoustid=args.delay,
                  delay_mb=args.delay_mb)
    print()
    print_stats(conn)


if __name__ == "__main__":
    main()
