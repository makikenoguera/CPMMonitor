#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# CPM Tracks - Script de compilación para macOS
# Genera un .app y opcionalmente un .dmg para distribución
# Requiere: pip install pyinstaller rumps PyQt6
# ─────────────────────────────────────────────────────────────────────────────

set -e

APP_NAME="CPMTracks"
VERSION="1.0.0"
BUNDLE_ID="com.cpmtracks.agent"

# Directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " CPM Tracks — Build macOS v$VERSION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Limpiar builds anteriores
rm -rf build dist

# Verificar que existen los recursos
for f in assets/logo.png assets/icon.png assets/icon.icns; do
    if [ ! -f "$f" ]; then
        echo "⚠️  Falta: $f (la app compilará pero sin ese recurso)"
    fi
done

# Build con PyInstaller
pyinstaller \
    --noconsole \
    --windowed \
    --name "$APP_NAME" \
    --icon "assets/icon.icns" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --add-data "assets/logo.png:." \
    --add-data "assets/icon.png:." \
    --hidden-import "rumps" \
    --hidden-import "PyQt6.QtWidgets" \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --collect-all "rumps" \
    --paths "." \
    main.py

echo ""
echo "✓ .app generado en: dist/$APP_NAME.app"

# ── Generar .dmg para distribución ──────────────────────────────────────────
if command -v create-dmg &> /dev/null; then
    echo ""
    echo "Generando .dmg..."
    create-dmg \
        --volname "CPM Tracks $VERSION" \
        --volicon "assets/icon.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "$APP_NAME.app" 175 190 \
        --hide-extension "$APP_NAME.app" \
        --app-drop-link 425 190 \
        "dist/${APP_NAME}-${VERSION}.dmg" \
        "dist/$APP_NAME.app"
    echo "✓ .dmg generado: dist/${APP_NAME}-${VERSION}.dmg"
else
    echo "ℹ️  create-dmg no instalado. Para generar .dmg:"
    echo "   brew install create-dmg"
    echo "   y volver a correr este script"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Build completo ✓"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
