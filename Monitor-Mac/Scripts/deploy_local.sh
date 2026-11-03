#!/bin/bash
# deploy_local.sh — build, instala y re-firma con identidad estable para que TCC persista
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="SumarteRed Monitor"
INSTALL_PATH="/Applications/${APP_NAME}.app"
SIGN_IDENTITY="Apple Development: manuel.noguera@gmail.com (A5XT6UB6FK)"
BUNDLE_ID="com.sumartered.monitor"

echo "▶ Build..."
xcodebuild -project "$PROJECT_DIR/SumarteRedMonitor.xcodeproj" \
           -scheme SumarteRedMonitor \
           -configuration Debug build \
           | tail -3

BUILD=$(find ~/Library/Developer/Xcode/DerivedData/SumarteRedMonitor-*/Build/Products/Debug -name "SumarteRedMonitor.app" -maxdepth 1 | head -1)
[ -z "$BUILD" ] && echo "❌ No se encontró el build" && exit 1

echo "▶ Detener app..."
pkill -f "SumarteRedMonit" 2>/dev/null; sleep 1

echo "▶ Instalar en $INSTALL_PATH..."
rm -rf "$INSTALL_PATH"
cp -R "$BUILD" "$INSTALL_PATH"

echo "▶ Re-firmar con identidad estable (TCC persiste)..."
codesign --force --deep --sign "$SIGN_IDENTITY" "$INSTALL_PATH" 2>&1 && \
    echo "   ✅ Firmado: $SIGN_IDENTITY" || \
    echo "   ⚠️  Firma falló — TCC pedirá permiso de nuevo"

echo "▶ Lanzar..."
open "$INSTALL_PATH"

echo "✅ Listo — $(date)"
