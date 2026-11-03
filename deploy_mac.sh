#!/bin/bash
# deploy_mac.sh — Build, firma y despliega SumarteRed Monitor
# Firma con certificado Apple Development → TCC persiste entre rebuilds
set -e

PROJECT="/Users/macbookpro/CPMTracks/Monitor-Mac/SumarteRedMonitor.xcodeproj"
SCHEME="SumarteRedMonitor"
DERIVED="/Users/macbookpro/Library/Developer/Xcode/DerivedData/SumarteRedMonitor-gpltilsfdhjcbocakxliixwgsnlb/Build/Products/Release/SumarteRedMonitor.app"
DEST="/Applications/SumarteRed Monitor.app"
CERT="9AD5722A2DE24520221FDCEFA97E2BBE62DBC891"  # Apple Development: manuel.noguera@gmail.com

echo "🔨 Building..."
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration Release \
  CODE_SIGNING_ALLOWED=NO \
  -quiet

echo "🛑 Cerrando app..."
pkill -x SumarteRedMonitor 2>/dev/null || true
sleep 1

echo "📦 Instalando (preservando bundle para TCC)..."
# IMPORTANTE: NO usar rm -rf porque macOS revoca kTCCServiceScreenCapture
# cuando se destruye y recrea el bundle. rsync actualiza el contenido
# sin eliminar el .app, preservando la identidad TCC del bundle.
if [ ! -d "$DEST" ]; then
    cp -Rf "$DERIVED" "$DEST"
else
    rsync -a --delete "$DERIVED/" "$DEST/"
fi

echo "🔏 Firmando con Apple Development..."
codesign --force --deep --sign "$CERT" "$DEST"

echo "🚀 Iniciando..."
open "$DEST"

echo "✅ Deploy completo — firma persistente, no requiere re-aprobar permiso"
