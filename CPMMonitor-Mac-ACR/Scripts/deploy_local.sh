#!/bin/bash
# deploy_local.sh — build y actualiza /Applications sin perder el permiso TCC
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="SumarteRed Monitor"
INSTALL_PATH="/Applications/${APP_NAME}.app"

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

echo "▶ Lanzar..."
open "$INSTALL_PATH"

echo "✅ Listo — $(date)"
