#!/usr/bin/env python3
"""
CPM Music Renamer
=================
Limpia nombres de carpetas y archivos de música:
  · Quita números iniciales (01., 002., 001_ etc.)
  · Quita emojis e iconos Unicode
  · Quita "Iframe" (prefijo de embeds de YouTube)
  · Quita IDs de YouTube entre corchetes [abc123xyz]
  · Quita marcadores de contenido: (copia), (letra), (oficial), (video oficial),
    (lyric video), [ Letra Official ], (audio), (con letra), (128 kbps), etc.
  · Quita segmentos que son solo marcadores: "- Video Oficial -", "- Lyric Video"
  · Convierte a Title Case inteligente (no TODO MAYÚSCULAS)
  · Detecta formato "CANCION  ARTISTA" (doble espacio) y lo convierte a "Artista - Cancion"
  · Normaliza extensión a minúsculas (.MP3 → .mp3)
  · Procesa subcarpetas recursivamente (--recursivo)

Uso:
  python3 rename_music.py /ruta/carpeta                        ← preview (no modifica nada)
  python3 rename_music.py /ruta/carpeta --ejecutar             ← aplica los cambios
  python3 rename_music.py /ruta/carpeta --solo-archivos        ← no renombra la carpeta raíz
  python3 rename_music.py /ruta/carpeta --recursivo --ejecutar ← procesa subcarpetas también
"""

import os, re, sys, unicodedata, argparse
from pathlib import Path

# ─── Palabras que van en minúsculas en Title Case (español + inglés) ───────
MINOR_WORDS = {
    'de','del','la','las','los','el','en','y','a','con','por','para','al',
    'e','o','u','ni','mas','pero','sino','aunque',
    'of','the','a','an','in','on','at','by','and','or','but','nor','for',
    'ft','feat','vs','x',
}

# ─── Marcadores que al ser un segmento completo (entre " - ") se eliminan ──
_MARKER_SEGMENTS = {
    'video oficial', 'official video', 'lyric video', 'video lyric',
    'letra oficial', 'letra official', 'official lyric', 'lyrics',
    'video letra', 'letra', 'audio', 'hd', 'hq', 'oficial', 'official',
    'music video', 'official music video', 'con letra',
    'lyric', 'visualizer', 'audio oficial', 'lyric oficial',
}

# ─── Quitar emojis y símbolos Unicode ──────────────────────────────────────
_EMOJI_RE = re.compile(
    "["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F6FF"
    u"\U0001F700-\U0001F77F"
    u"\U0001F780-\U0001F7FF"
    u"\U0001F800-\U0001F8FF"
    u"\U0001F900-\U0001F9FF"
    u"\U0001FA00-\U0001FA6F"
    u"\U0001FA70-\U0001FAFF"
    u"\U00002702-\U000027B0"
    u"\U000024C2-\U0001F251"
    u"\U0001f926-\U0001f937"
    u"\U00010000-\U0010ffff"
    u"♀-♂"
    u"☀-⭕"
    u"‍"
    u"⏏⏩⌚"
    u"️〰"
    "]+",
    re.UNICODE
)
_EXTRA_SYMBOLS = re.compile(r'[❌✅⭐🌟💥🔥💯👑🎵🎶🎤🎧×✗✘]')

def quitar_emojis(texto: str) -> str:
    texto = _EMOJI_RE.sub('', texto)
    texto = _EXTRA_SYMBOLS.sub('', texto)
    return texto

# ─── Quitar número inicial (soporta 01. / 01- / 001_ / 01 ) ────────────────
_NUM_PREFIJO = re.compile(r'^\d+[\.\-_\s]+\s*')

def quitar_numero_inicial(nombre: str) -> str:
    return _NUM_PREFIJO.sub('', nombre).strip()

# ─── Quitar marcadores de contenido ────────────────────────────────────────

# 1. "Iframe" al inicio o en cualquier posición como palabra
_IFRAME_RE = re.compile(r'\bIframe\b\s*', re.IGNORECASE)

# 2. IDs de YouTube: [abc123def], [_tuuxgo_yn0], [abc-def_ghi], [abc - def]
_YTID_RE = re.compile(r'\s*\[\s*[a-z0-9_][a-z0-9_\-\s]{3,18}[a-z0-9_]\s*\]\s*', re.IGNORECASE)

# 3. Marcadores dentro de paréntesis ( )
_PAREN_MARKERS = re.compile(
    r'\(\s*(?:'
    r'copia'
    r'|letra\s*oficial|letra\s*official|letra\s*lyrics?'
    r'|lyric[s]?\s*video|video\s*lyric[s]?'
    r'|video\s*letra|letra'
    r'|con\s*letra'
    r'|video\s*oficial|official\s*video'
    r'|official\s*music\s*video|music\s*video'
    r'|official\s*lyric[s]?|lyric[s]?\s*oficial'
    r'|visualizer'
    r'|oficial|official'
    r'|audio\s*oficial|audio'
    r'|hd|hq'
    r'|(?:128|192|256|320)\s*kbps'
    r')\s*\)',
    re.IGNORECASE
)

# 4. Marcadores dentro de corchetes [ ] (distintos de los IDs de YouTube)
_BRACKET_MARKERS = re.compile(
    r'\[\s*(?:'
    r'letra\s*oficial|letra\s*official|letra\s*lyrics?'
    r'|lyric[s]?\s*video|video\s*lyric[s]?'
    r'|video\s*letra|letra'
    r'|con\s*letra'
    r'|video\s*oficial|official\s*video'
    r'|official\s*music\s*video|music\s*video'
    r'|official\s*lyric[s]?|lyric[s]?\s*oficial'
    r'|visualizer'
    r'|oficial|official'
    r'|audio\s*oficial|audio'
    r'|hd|hq'
    r')\s*\]',
    re.IGNORECASE
)

# 5. (N) duplicado numérico suelto — e.g. (1), (2)  (pero no (1997) años)
_DUP_NUM_RE = re.compile(r'\s*\(\d{1,2}\)\s*')

# 6. Paréntesis vacíos: ( ) o ()
_EMPTY_PAREN_RE = re.compile(r'\(\s*\)')

# 7. Marcadores inline dentro de un segmento (sin guiones separadores)
#    e.g. "Artista Video Oficial - Cancion" → "Artista - Cancion"
_INLINE_MARKERS = re.compile(
    r'\s+\b(?:video\s+oficial|official\s+video|lyric\s+video|video\s+lyric'
    r'|letra\s+oficial|letra\s+official|audio\s+oficial|music\s+video'
    r'|official\s+music\s+video|video\s+letra)\b',
    re.IGNORECASE
)


def quitar_marcadores(nombre: str) -> str:
    """Elimina Iframe, IDs de YouTube, (copia), marcadores letra/video/oficial.
    IMPORTANTE: NO colapsa espacios dobles — el separador 'CANCION  ARTISTA'
    debe preservarse para que la detección posterior funcione."""
    nombre = _IFRAME_RE.sub('', nombre)
    nombre = _YTID_RE.sub(' ', nombre)
    nombre = _PAREN_MARKERS.sub(' ', nombre)
    nombre = _BRACKET_MARKERS.sub(' ', nombre)
    nombre = _DUP_NUM_RE.sub(' ', nombre)
    nombre = _EMPTY_PAREN_RE.sub(' ', nombre)
    nombre = _INLINE_MARKERS.sub('', nombre)
    # Solo colapsar 3+ espacios → 2 (preservar el doble-espacio separador)
    nombre = re.sub(r' {3,}', '  ', nombre).strip()
    return nombre


def quitar_segmentos_marcador(nombre: str) -> str:
    """Elimina segmentos completos entre ' - ' que sean solo marcadores conocidos.
    Ej: 'Artista - Cancion - Video Oficial' → 'Artista - Cancion'
        'Lyric Video - Artista - Cancion'   → 'Artista - Cancion'
    """
    partes = [p.strip() for p in nombre.split(' - ')]
    partes_limpias = [p for p in partes if p.lower() not in _MARKER_SEGMENTS and p]
    return ' - '.join(partes_limpias)


# ─── Title Case inteligente ─────────────────────────────────────────────────
def title_case(texto: str) -> str:
    """Title Case inteligente: baja todo primero, luego capitaliza.
    Siempre capitaliza la primera palabra de cada segmento separado por ' - '."""
    segmentos = texto.split(' - ')
    segmentos_resultado = []

    for segmento in segmentos:
        palabras = segmento.split()
        resultado = []
        for i, p in enumerate(palabras):
            p_lower = p.lower()
            if '-' in p and p not in ('-',):
                p = '-'.join(part.lower().capitalize() for part in p.split('-'))
            elif i == 0 or p_lower not in MINOR_WORDS:
                p = p_lower[0].upper() + p_lower[1:] if p_lower else p_lower
            else:
                p = p_lower
            resultado.append(p)
        segmentos_resultado.append(' '.join(resultado))

    return ' - '.join(segmentos_resultado)


# ─── Limpiar nombre base ────────────────────────────────────────────────────
def limpiar_nombre(nombre: str) -> str:
    """Aplica todas las limpiezas al nombre (sin extensión)."""
    # NFC: convierte NFD (a + combining accent) → á compuesto
    nombre = unicodedata.normalize('NFC', nombre)

    # Quitar emojis e iconos
    nombre = quitar_emojis(nombre)

    # Quitar Iframe, IDs YouTube, (copia), marcadores letra/video/oficial
    nombre = quitar_marcadores(nombre)

    # Quitar número inicial (01. / 01- / 001_ / etc.)
    nombre = quitar_numero_inicial(nombre)

    # Detectar formato "CANCION  ARTISTA" (2+ espacios como separador)
    # → convertir a "Artista - Cancion"
    partes = re.split(r'  +', nombre)
    if len(partes) == 2:
        cancion = partes[0].strip()
        artista = partes[1].strip()
        # Quitar sufijo de duplicado al final del artista: " (1)", " (2)", etc.
        artista = re.sub(r'\s*\(\d+\)\s*$', '', artista).strip()
        nombre  = f"{artista} - {cancion}"
    else:
        nombre = nombre.strip()

    # Quitar segmentos completos que son solo marcadores
    nombre = quitar_segmentos_marcador(nombre)

    # Limpiar múltiples espacios
    nombre = re.sub(r' {2,}', ' ', nombre)

    # Quitar caracteres raros que puedan quedar
    nombre = re.sub(r'[^\w\s\-\.,&\(\)\[\]\'áéíóúÁÉÍÓÚüÜñÑ]', '', nombre)

    # Title Case
    nombre = title_case(nombre)

    # Normalizar espacios alrededor del guión separador
    nombre = re.sub(r'\s*-\s*', ' - ', nombre)

    # Quitar guiones sobrantes al inicio o al final
    nombre = nombre.strip(' -').strip()

    return nombre


def colisiona(orig: Path, nuevo: Path) -> bool:
    """¿`nuevo` ya lo ocupa algo distinto de `orig`?

    En APFS/HFS+ (case-insensitive) `CPMTracks` y `Cpmtracks` son el mismo
    inodo, así que `nuevo.exists()` da True aunque solo cambien mayúsculas.
    """
    if not nuevo.exists():
        return False
    try:
        return not nuevo.samefile(orig)
    except OSError:
        return True


# ─── Procesar un directorio ─────────────────────────────────────────────────
def procesar_carpeta(ruta_carpeta: Path,
                     ejecutar: bool = False,
                     renombrar_carpeta_raiz: bool = True,
                     recursivo: bool = False,
                     _es_subdir: bool = False):
    """
    Procesa una carpeta y opcionalmente sus subcarpetas.
    _es_subdir=True omite el mensaje de encabezado para subcarpetas silenciosas.
    """
    ruta_carpeta = Path(ruta_carpeta).resolve()
    if not ruta_carpeta.is_dir():
        print(f"❌ No es una carpeta válida: {ruta_carpeta}")
        sys.exit(1)

    cambios_carpeta  = []
    cambios_archivos = []
    sin_cambios      = 0
    subdirs          = []

    # ── Iterar contenido de la carpeta ─────────────────────────────────────
    for item in sorted(ruta_carpeta.iterdir()):
        if item.name.startswith('._'):
            continue

        if item.is_dir():
            subdirs.append(item)
            # También renombrar la subcarpeta si corresponde
            nuevo_nombre_dir = limpiar_nombre(item.name)
            orig_dir_nfc = unicodedata.normalize('NFC', item.name)
            if nuevo_nombre_dir != orig_dir_nfc:
                cambios_carpeta.append((item, ruta_carpeta / nuevo_nombre_dir))

        elif item.is_file():
            ext = item.suffix.lower()
            if ext not in ('.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg'):
                continue
            nuevo_stem   = limpiar_nombre(item.stem)
            nuevo_nombre = nuevo_stem + ext
            # Comparar en NFC para evitar falsa detección NFD↔NFC en APFS/macOS
            orig_nfc = unicodedata.normalize('NFC', item.stem) + ext
            if nuevo_nombre != orig_nfc:
                cambios_archivos.append((item, ruta_carpeta / nuevo_nombre))
            else:
                sin_cambios += 1

    # ── Renombrar la carpeta raíz si aplica ────────────────────────────────
    # (solo si es la raíz del comando y el flag está activo)
    cambios_raiz = []
    if renombrar_carpeta_raiz and not _es_subdir:
        nombre_carpeta       = ruta_carpeta.name
        nuevo_nombre_carpeta = limpiar_nombre(nombre_carpeta)
        orig_raiz_nfc        = unicodedata.normalize('NFC', nombre_carpeta)
        if nuevo_nombre_carpeta != orig_raiz_nfc:
            cambios_raiz.append((ruta_carpeta, ruta_carpeta.parent / nuevo_nombre_carpeta))

    # ── Mostrar preview ────────────────────────────────────────────────────
    total_cambios = len(cambios_raiz) + len(cambios_carpeta) + len(cambios_archivos)

    print(f"\n{'🔍 PREVIEW' if not ejecutar else '✏️  EJECUTANDO'} — {ruta_carpeta.name}")
    print("─" * 70)

    if cambios_raiz:
        print("\n📁 CARPETA RAÍZ:")
        for orig, nuevo in cambios_raiz:
            print(f"  ANTES : {orig.name}")
            print(f"  DESPUÉS: {nuevo.name}")

    if cambios_carpeta:
        print(f"\n📂 SUBCARPETAS ({len(cambios_carpeta)} cambios):")
        for orig, nuevo in cambios_carpeta:
            print(f"  [{orig.name}]")
            print(f"   → {nuevo.name}")

    if cambios_archivos:
        print(f"\n🎵 ARCHIVOS ({len(cambios_archivos)} cambios):")
        for orig, nuevo in cambios_archivos:
            print(f"  [{orig.name}]")
            print(f"   → {nuevo.name}")

    print(f"\n  Total cambios : {total_cambios}")
    print(f"  Sin cambios   : {sin_cambios}")

    if not ejecutar:
        print("\n  ⚠️  Modo PREVIEW — no se modificó nada.")
        print("      Agrega --ejecutar para aplicar los cambios.")
        # Continuar preview en subdirectorios si --recursivo
        if recursivo:
            for sub in subdirs:
                procesar_carpeta(sub, ejecutar=False, renombrar_carpeta_raiz=True,
                                 recursivo=True, _es_subdir=True)
        return

    # ── Ejecutar cambios ───────────────────────────────────────────────────
    errores = 0

    # 1. Archivos primero
    for orig, nuevo in cambios_archivos:
        try:
            if colisiona(orig, nuevo):
                base = nuevo.stem; ext = nuevo.suffix
                nuevo = nuevo.parent / f"{base} (dup){ext}"
                print(f"  ⚠️  Colisión: renombrado a {nuevo.name}")
            orig.rename(nuevo)
        except Exception as e:
            print(f"  ❌ Error {orig.name}: {e}")
            errores += 1

    # 2. Subcarpetas (con rutas actualizadas antes de recursión)
    nuevas_rutas_subs = []
    for orig, nuevo in cambios_carpeta:
        try:
            if colisiona(orig, nuevo):
                nuevo = nuevo.parent / f"{nuevo.name} (dup)"
                print(f"  ⚠️  Colisión carpeta: renombrado a {nuevo.name}")
            orig.rename(nuevo)
            nuevas_rutas_subs.append(nuevo)
        except Exception as e:
            print(f"  ❌ Error carpeta {orig.name}: {e}")
            errores += 1
            nuevas_rutas_subs.append(orig)  # mantener original si falló

    # Subdirs no renombrados
    subdirs_renombrados = set(orig for orig, _ in cambios_carpeta)
    for sub in subdirs:
        if sub not in subdirs_renombrados:
            nuevas_rutas_subs.append(sub)

    # 3. Carpeta raíz al final
    nueva_raiz = ruta_carpeta
    for orig, nuevo in cambios_raiz:
        try:
            orig.rename(nuevo)
            nueva_raiz = nuevo
        except Exception as e:
            print(f"  ❌ Error carpeta raíz {orig.name}: {e}")
            errores += 1

    print(f"\n  ✅ {total_cambios - errores} cambios aplicados  ·  {errores} errores")

    # 4. Recursión en subdirectorios con rutas actualizadas
    if recursivo:
        for sub in nuevas_rutas_subs:
            if sub.is_dir():
                errores += procesar_carpeta(sub, ejecutar=True, renombrar_carpeta_raiz=True,
                                            recursivo=True, _es_subdir=True) or 0

    return errores


# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="CPM Music Renamer — limpia nombres de carpetas y archivos de música"
    )
    parser.add_argument("carpeta",
                        help="Ruta a la carpeta que se va a procesar")
    parser.add_argument("--ejecutar", action="store_true",
                        help="Aplicar los cambios (por defecto solo muestra preview)")
    parser.add_argument("--solo-archivos", action="store_true",
                        help="No renombrar la carpeta raíz, solo los archivos dentro")
    parser.add_argument("--recursivo", action="store_true",
                        help="Procesar también todas las subcarpetas")
    args = parser.parse_args()

    # Path("") resuelve al directorio actual: una variable de shell vacía
    # convertiría esto en un renombrado masivo del cwd.
    if not args.carpeta.strip():
        print("❌ Ruta vacía. Pasa una carpeta explícita.")
        sys.exit(2)

    errores = procesar_carpeta(
        ruta_carpeta=args.carpeta,
        ejecutar=args.ejecutar,
        renombrar_carpeta_raiz=not args.solo_archivos,
        recursivo=args.recursivo,
    )
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
