#!/bin/bash
# Setup del servidor SumarteRed Monitor v3.0
# Ejecutar desde /Users/macbookpro/CPMTracks/server/

set -e

echo "🎵 SumarteRed Monitor Server — Setup"
echo "======================================"

# 1. Python virtual env
echo ""
echo "1. Creando entorno virtual…"
python3 -m venv venv
source venv/bin/activate

# 2. Dependencias
echo ""
echo "2. Instalando dependencias…"
pip install -q -r requirements.txt

# 3. Variables de entorno
echo ""
echo "3. Configurando variables de entorno…"

if [ ! -f .env ]; then
cat > .env << 'EOF'
# API key de AcousticID (gratis en https://acoustid.org/login)
ACOUSTID_API_KEY=your_acoustid_api_key_here

# Rutas de las bases de datos
FINGERPRINTS_DB=../FingerprintBuilder/fingerprints.db
PLAYS_DB=./plays.db
VENUES_DB=./venues.db

# Puerto del servidor
PORT=8000

# Umbral de confianza mínimo para identificación (0.0 - 1.0)
SCORE_THRESHOLD=0.80
EOF
echo "   ✅ Creado .env — EDITA ACOUSTID_API_KEY antes de arrancar"
else
echo "   ℹ️  .env ya existe"
fi

# 4. Inicializar
echo ""
echo "4. Inicializando bases de datos…"
source .env 2>/dev/null || true
python3 -c "
import sys
sys.path.insert(0, '.')
from main import init_plays_db, init_venues_db
init_plays_db()
init_venues_db()
print('   ✅ Bases de datos listas')
"

echo ""
echo "======================================"
echo "✅ Setup completado"
echo ""
echo "Para arrancar el servidor:"
echo "  source venv/bin/activate"
echo "  export ACOUSTID_API_KEY=tu_api_key"
echo "  python main.py"
echo ""
echo "O con recarga automática:"
echo "  uvicorn main:app --reload --port 8000"
echo ""
echo "Endpoints disponibles:"
echo "  GET  /health"
echo "  GET  /v1/venue/:id          (X-API-Key requerida)"
echo "  POST /v1/identify           (X-API-Key requerida)"
echo "  POST /v1/plays              (X-API-Key requerida)"
echo "  GET  /admin/stats"
echo "  POST /admin/venues"
echo ""
echo "Venue de prueba creado:"
echo "  venue_id: VENUE-001"
echo "  api_key:  demo-key-sumartered-2024"
