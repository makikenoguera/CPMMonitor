#!/usr/bin/env bash
# build_pkg.sh — Compila SumarteRedMonitor y genera un instalador .pkg para pruebas
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_NAME="SumarteRedMonitor"
SCHEME="SumarteRedMonitor"
BUNDLE_ID="com.cpmtracks.SumarteRedMonitor"
VERSION=$(defaults read "$ROOT/SumarteRedMonitor/Info.plist" CFBundleShortVersionString 2>/dev/null || echo "1.0.0")
BUILD=$(defaults read "$ROOT/SumarteRedMonitor/Info.plist" CFBundleVersion 2>/dev/null || echo "1")

ARCHIVE_PATH="$ROOT/build/${APP_NAME}.xcarchive"
EXPORT_PATH="$ROOT/build/export"
PKG_PATH="$ROOT/build/${APP_NAME}-${VERSION}.pkg"
APP_PATH="$EXPORT_PATH/${APP_NAME}.app"

echo "=== CPM Monitor — Build & Package ==="
echo "Versión : $VERSION ($BUILD)"
echo "Root    : $ROOT"
echo ""

# Limpiar build anterior
rm -rf "$ROOT/build"
mkdir -p "$ROOT/build"

# Asegurarse de usar Xcode.app (no solo CLT)
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

# 1. Archivar (sin firma para pruebas internas)
echo "➡  Archivando…"
xcodebuild archive \
    -project "$ROOT/${APP_NAME}.xcodeproj" \
    -scheme "$SCHEME" \
    -configuration Release \
    -archivePath "$ARCHIVE_PATH" \
    CODE_SIGN_IDENTITY="-" \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGNING_ALLOWED=NO \
    ONLY_ACTIVE_ARCH=NO \
    | tail -5

echo "✅ Archivado en: $ARCHIVE_PATH"

# 2. Exportar .app
echo "➡  Exportando .app…"
mkdir -p "$EXPORT_PATH"
cp -R "$ARCHIVE_PATH/Products/Applications/${APP_NAME}.app" "$EXPORT_PATH/"

echo "✅ App exportada en: $APP_PATH"

# 3. Crear estructura del instalador
echo "➡  Creando instalador .pkg…"
PKG_STAGE="$ROOT/build/pkg_stage"
INSTALL_DIR="$PKG_STAGE/Applications"
mkdir -p "$INSTALL_DIR"
cp -R "$APP_PATH" "$INSTALL_DIR/"

# 4. Generar componente pkg
pkgbuild \
    --root "$PKG_STAGE" \
    --identifier "$BUNDLE_ID" \
    --version "$VERSION" \
    --install-location "/" \
    "$PKG_PATH"

echo ""
echo "====================================="
echo "✅ Instalador listo: $PKG_PATH"
echo "====================================="
echo ""
echo "Para instalar en este equipo:"
echo "  sudo installer -pkg \"$PKG_PATH\" -target /"
echo ""
echo "Distribuye el .pkg a tus testers."
