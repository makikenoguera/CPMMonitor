#!/bin/bash
# distribute.sh — build release, bundle fpcalc, firmar, empaquetar en .zip
# Resultado: SumarteRed Monitor.zip en el directorio del proyecto
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="SumarteRed Monitor"
SIGN_IDENTITY="Apple Development: manuel.noguera@gmail.com (A5XT6UB6FK)"
OUTPUT_DIR="$PROJECT_DIR/dist"

echo "▶ Limpiando dist/"
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# ── 1. Build Release ────────────────────────────────────────────────────────
echo "▶ Build Release…"
xcodebuild \
  -project "$PROJECT_DIR/SumarteRedMonitor.xcodeproj" \
  -scheme SumarteRedMonitor \
  -configuration Release \
  -derivedDataPath /tmp/cpm_dist_build \
  build 2>&1 | tail -5

BUILD_APP=$(find /tmp/cpm_dist_build/Build/Products/Release -name "SumarteRedMonitor.app" -maxdepth 1 | head -1)
[ -z "$BUILD_APP" ] && echo "❌ Build no encontrado" && exit 1
echo "   ✅ Build: $BUILD_APP"

# ── 2. Copiar a dist/ ───────────────────────────────────────────────────────
DIST_APP="$OUTPUT_DIR/${APP_NAME}.app"
cp -R "$BUILD_APP" "$DIST_APP"

# ── 3. Bundlear fpcalc con sus dylibs ───────────────────────────────────────
echo "▶ Bundleando fpcalc…"
HELPERS="$DIST_APP/Contents/Helpers"
LIBS_DIR="$DIST_APP/Contents/lib"
mkdir -p "$HELPERS" "$LIBS_DIR"

# Buscar fpcalc en el sistema
FPCALC_SRC=$(ls /opt/homebrew/bin/fpcalc /usr/local/bin/fpcalc 2>/dev/null | head -1)

if [ -z "$FPCALC_SRC" ]; then
    echo "   ⚠️  fpcalc no encontrado. Instalar: brew install chromaprint"
else
    cp "$FPCALC_SRC" "$HELPERS/fpcalc"
    chmod +x "$HELPERS/fpcalc"
    echo "   ✅ fpcalc copiado: $(file "$HELPERS/fpcalc" | awk -F: '{print $2}')"

    # Bundle all non-system dylibs recursively
    python3 - "$HELPERS/fpcalc" "$LIBS_DIR" << 'PYEOF'
import subprocess, shutil, sys, os
from pathlib import Path

binary = sys.argv[1]
libs_dir = Path(sys.argv[2])
SYSTEM_PREFIXES = ('/usr/lib/', '/System/', '@executable_path', '@loader_path', '@rpath/libSystem')
HOMEBREW_ROOTS = ['/usr/local/lib', '/opt/homebrew/lib',
                  '/usr/local/opt', '/opt/homebrew/opt']

def get_deps(path):
    try:
        out = subprocess.check_output(['otool', '-L', path], stderr=subprocess.DEVNULL).decode()
        return [line.strip().split(' ')[0] for line in out.strip().splitlines()[1:]]
    except:
        return []

def is_system(dep):
    return any(dep.startswith(p) for p in SYSTEM_PREFIXES)

def dep_name(dep):
    """The filename that consumers expect (not realpath)."""
    if dep.startswith('@rpath/'):
        return dep[len('@rpath/'):]
    return os.path.basename(dep)

def resolve(dep, extra_roots):
    """Find the actual file for a dependency."""
    if dep.startswith('@rpath/'):
        lib = dep[len('@rpath/'):]
        search = extra_roots + HOMEBREW_ROOTS
        for root in search:
            for candidate in [
                os.path.join(root, lib),
                # also try under opt/<name>/lib/<name>
            ]:
                if os.path.exists(candidate):
                    return os.path.realpath(candidate)
        return None
    if dep.startswith('@loader_path/'):
        return None
    if os.path.exists(dep):
        return os.path.realpath(dep)
    return None

# Seed extra roots from initial deps
extra_roots = []
for dep in get_deps(binary):
    if not is_system(dep) and os.path.exists(dep):
        extra_roots.append(os.path.dirname(os.path.realpath(dep)))

processed_names = set()
to_process = [(d, dep_name(d)) for d in get_deps(binary)]

while to_process:
    dep, name = to_process.pop(0)
    if name in processed_names:
        continue
    if is_system(dep):
        continue

    real = resolve(dep, extra_roots)
    if not real:
        print(f"   ⚠️  Cannot resolve: {dep}")
        continue

    processed_names.add(name)
    dest = libs_dir / name

    if not dest.exists():
        shutil.copy2(real, dest)
        os.chmod(dest, 0o755)
        # Fix this lib's own ID to match the name callers expect
        subprocess.run(['install_name_tool', '-id', f'@rpath/{name}', str(dest)],
                       stderr=subprocess.DEVNULL)
        print(f"   📦 {name}")
        extra_roots.append(os.path.dirname(real))

    # Queue transitive deps
    for sub_dep in get_deps(str(dest)):
        sub_name = dep_name(sub_dep)
        if sub_name not in processed_names and not is_system(sub_dep):
            to_process.append((sub_dep, sub_name))

# Fix cross-references between bundled libs
for dylib in libs_dir.iterdir():
    for dep in get_deps(str(dylib)):
        name = dep_name(dep)
        if (libs_dir / name).exists() and not dep.startswith('@rpath/'):
            subprocess.run(['install_name_tool', '-change', dep, f'@rpath/{name}', str(dylib)],
                           stderr=subprocess.DEVNULL)

print(f"   ✅ {len(list(libs_dir.iterdir()))} dylibs bundled into Contents/lib/")
PYEOF

    # Fix rpaths: fpcalc → @executable_path/../lib/
    # First, remove existing rpaths
    for rpath in $(otool -l "$HELPERS/fpcalc" 2>/dev/null | grep -A2 "LC_RPATH" | grep "path " | awk '{print $2}'); do
        install_name_tool -delete_rpath "$rpath" "$HELPERS/fpcalc" 2>/dev/null || true
    done
    install_name_tool -add_rpath "@executable_path/../lib" "$HELPERS/fpcalc" 2>/dev/null || true

    # Rewrite absolute lib paths in fpcalc binary to @rpath/name
    for dep in $(otool -L "$HELPERS/fpcalc" 2>/dev/null | awk '{print $1}' | tail -n +2); do
        dep_name=$(basename "$dep")
        if [ -f "$LIBS_DIR/$dep_name" ] && [[ "$dep" != @* ]]; then
            install_name_tool -change "$dep" "@rpath/$dep_name" "$HELPERS/fpcalc" 2>/dev/null || true
        fi
    done

    echo "   ✅ fpcalc bundleado con dylibs"
fi

# ── 4. Firmar ───────────────────────────────────────────────────────────────
echo "▶ Firmando con $SIGN_IDENTITY…"
# Sign all dylibs first (--deep doesn't reliably cover Contents/lib/)
for dylib in "$DIST_APP/Contents/lib/"*.dylib; do
    [ -f "$dylib" ] || continue
    codesign --force --sign "$SIGN_IDENTITY" "$dylib" 2>/dev/null || \
    codesign --force --sign - "$dylib" 2>/dev/null || true  # ad-hoc fallback
done
# Sign the whole app (includes fpcalc in Helpers)
codesign --force --deep --sign "$SIGN_IDENTITY" \
  --options runtime \
  "$DIST_APP" 2>&1 && echo "   ✅ Firmado" || echo "   ⚠️  Firma falló (continuando)"

# ── 5. Verificar firma ──────────────────────────────────────────────────────
codesign --verify --verbose "$DIST_APP" 2>&1 | head -3

# ── 6. Empaquetar en .zip ───────────────────────────────────────────────────
echo "▶ Creando ZIP…"
cd "$OUTPUT_DIR"
zip -r --symlinks "${APP_NAME}.zip" "${APP_NAME}.app" 2>/dev/null
ZIP_SIZE=$(du -sh "${APP_NAME}.zip" | awk '{print $1}')
echo "   ✅ ${APP_NAME}.zip — $ZIP_SIZE"
echo ""
echo "📦 Listo: $OUTPUT_DIR/${APP_NAME}.zip"
echo ""
echo "ℹ️  Para instalar en otra Mac:"
echo "   1. Descomprimir el ZIP"
echo "   2. Copiar '${APP_NAME}.app' a /Applications"
echo "   3. IMPORTANTE: primera vez → clic derecho → Abrir (no doble clic)"
echo "      Esto pasa Gatekeeper sin Developer ID."
echo "   4. La app pedirá permiso de Grabación de Pantalla al primer uso."
