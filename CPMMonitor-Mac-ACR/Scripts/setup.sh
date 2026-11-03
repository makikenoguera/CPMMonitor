#!/usr/bin/env bash
# setup.sh — Instala dependencias y genera el proyecto Xcode
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== CPM Monitor — Setup ==="

# 1. Verificar Xcode
if ! xcode-select -p &>/dev/null; then
    echo "❌ Xcode Command Line Tools no encontrado."
    echo "   Ejecuta: xcode-select --install"
    exit 1
fi

# 2. Instalar XcodeGen (si no está)
if ! command -v xcodegen &>/dev/null; then
    echo "➡  Instalando XcodeGen…"
    if command -v brew &>/dev/null; then
        brew install xcodegen
    else
        echo "❌ Homebrew no encontrado. Instálalo en https://brew.sh y ejecuta: brew install xcodegen"
        exit 1
    fi
fi

echo "✅ XcodeGen: $(xcodegen --version)"

# 3. Generar proyecto Xcode
echo "➡  Generando CPMMonitor.xcodeproj…"
xcodegen generate --spec "$ROOT/project.yml"

echo ""
echo "✅ Proyecto generado en: $ROOT/CPMMonitor.xcodeproj"
echo ""
echo "Para abrir en Xcode:"
echo "   open \"$ROOT/CPMMonitor.xcodeproj\""
echo ""
echo "Para compilar y empaquetar:"
echo "   bash \"$ROOT/Scripts/build_pkg.sh\""
