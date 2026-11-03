# CPM — SumarteRed Music System
**Contexto para Claude · Nueva Etapa: Servidor + App + Dashboards**
*Última actualización: 2026-10-18*

---

## ¿Qué es este proyecto?

**SumarteRed** es un sistema de gestión y monitoreo de música para eventos/venues. El objetivo final es:
- Identificar qué canciones se reproducen en cada venue (sala, evento, casa)
- Registrar reproducciones con ISRC para reporte a entidades de derechos
- Dashboard web para administrador, artistas y venues
- Reporte mensual automático por email

---

## Etapa anterior (COMPLETADA ✅)

### Biblioteca musical limpiada
- **4,551 tracks** en `/Volumes/PARRA STU 2/SumarteRed Musica/`
- Formato estandarizado: `Artista - Cancion.mp3` (Title Case, sin números, sin emojis, sin marcadores)
- Script: `/Users/macbookpro/Cpmtracks (dup)/rename_music.py`
- 83+ carpetas procesadas (salsa, vallenato, popular colombiana, reguetón, etc.)

### FingerprintBuilder (EN PROCESO 🔄)
- Script: `/Users/macbookpro/Cpmtracks (dup)/FingerprintBuilder/build_fingerprints.py`
- DB: `/Users/macbookpro/Cpmtracks (dup)/FingerprintBuilder/fingerprints.db`
- Usa **fpcalc (Chromaprint)** para generar huellas acústicas
- Consulta **AcousticID + MusicBrainz** para obtener ISRC
- Estado al 2026-10-18: ~708/4551 procesados, 26 con ISRC, tasa ~0.6%
  - Tasa baja esperada: música colombiana regional poco representada en MusicBrainz
- Visor HTML: `/Users/macbookpro/Cpmtracks (dup)/FingerprintBuilder/visor_fingerprints.html`
  - Auto-recarga cada 5 min
  - Regenerar: `cd FingerprintBuilder && python3 generar_visor.py`

---

## Etapa actual: NUEVA FASE 🚀

### Foco: Servidor + App iOS + Dashboards

---

## Arquitectura del sistema

```
[App iOS en venue]
    │  graba 10-15s de audio
    │  genera fingerprint local (fpcalc)
    │  POST /v1/identify  →  [Servidor]
                                │
                          [PostgreSQL]
                          tabla: plays
                          tabla: tracks (fingerprints migrados desde SQLite)
                          tabla: venues
                          tabla: artists
                                │
                          [Dashboard Web]
                          /admin  → vista global
                          /venue  → por local
                          /artist → por artista
```

---

## Estado del código iOS (Swift)

### Archivo principal: AcousticIDClient.swift
**Bugs conocidos a corregir:**

1. **ISRC no se solicita correctamente**
   ```swift
   // ❌ Actual — no pide ISRCs
   "https://api.acoustid.org/v2/lookup?meta=recordings"
   // ✅ Correcto
   "https://api.acoustid.org/v2/lookup?meta=recordings+isrcs"
   ```

2. **idempotencyKey no determinista**
   ```swift
   // ❌ Actual — hashValue cambia entre ejecuciones
   let key = abs(normalized.hashValue)
   // ✅ Correcto — SHA-256 del filepath
   import CryptoKit
   let key = SHA256.hash(data: Data(normalized.utf8))
               .compactMap { String(format: "%02x", $0) }.joined()
   ```

3. **Session token expirado**
   - POST /v1/plays retorna 401
   - Necesita refresh de token o nuevo token de sesión

4. **fpcalc no está en el bundle**
   - Debe incluirse en: `Bundle.main.path(forResource: "fpcalc", ofType: nil)`
   - Compilar fpcalc para ARM64 (Apple Silicon) e incluir en app bundle

### Endpoint pendiente de crear en servidor:
```
POST /v1/identify
Body: { fingerprint: "...", duration: 254.5, venue_id: "uuid" }
Response: { track_id, artista, titulo, isrc, confianza }
```

---

## Base de datos

### SQLite local (fingerprints.db) — migrar a PostgreSQL en servidor

**Esquema actual tabla `tracks`:**
```sql
id, filepath, filename, extension,
artista_tag, titulo_tag, artista_final, titulo_final,
fingerprint, duration_seg,
mbid, isrc, isrc_fuente, isrc_estado,
afiliado, acoustid_score,
procesado, error,
created_at, updated_at
```

**Tablas nuevas a crear en PostgreSQL:**
```sql
-- Venues registrados
CREATE TABLE venues (
  id UUID PRIMARY KEY,
  nombre TEXT NOT NULL,
  ciudad TEXT,
  tipo TEXT, -- 'bar', 'restaurante', 'evento', 'casa'
  contacto_email TEXT,
  activo BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reproducciones detectadas
CREATE TABLE plays (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id UUID REFERENCES venues(id),
  track_id INTEGER REFERENCES tracks(id),
  isrc TEXT,
  artista TEXT,
  titulo TEXT,
  confianza FLOAT,
  played_at TIMESTAMPTZ DEFAULT NOW(),
  reportado BOOLEAN DEFAULT false
);
```

---

## Dashboards pendientes

### 1. Admin (`/admin`)
- Total plays del mes por venue
- Tracks más reproducidos (ranking)
- ISRCs identificados vs sin identificar
- Botón "Generar reporte mensual"

### 2. Venue (`/venue/:id`)
- Sus reproducciones del mes
- Artistas más tocados
- Exportar CSV para reporte

### 3. Artista (`/artist/:slug`)
- En qué venues suena
- Cuántas veces al mes
- Tendencia histórica

---

## Reporte mensual automático

- Cron job el día 1 de cada mes
- Email a cada venue con: lista de tracks reproducidos, ISRCs, conteo
- Email a admin con resumen global
- Stack sugerido: Python + SendGrid o Resend

---

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| App móvil | Swift (iOS) |
| Fingerprinting | fpcalc / Chromaprint |
| Identificación | AcousticID API + MusicBrainz |
| Servidor | Python (FastAPI) o Node.js |
| Base de datos | PostgreSQL |
| Dashboard | HTML/JS simple o Next.js |
| Email | SendGrid / Resend |
| Deploy | VPS (ya existe) o Railway/Render |

---

## Archivos clave locales

```
/Users/macbookpro/Cpmtracks (dup)/
├── rename_music.py                    # limpieza de nombres
├── CLAUDE.md                          # este archivo (contexto para Claude)
└── FingerprintBuilder/
    ├── build_fingerprints.py          # generador de fingerprints
    ├── fingerprints.db                # SQLite con 4,551 tracks
    ├── generar_visor.py               # genera el HTML viewer
    └── visor_fingerprints.html        # visor con auto-refresh 5min

/Volumes/PARRA STU 2/SumarteRed Musica/   # biblioteca limpiada (83+ carpetas)
```

---

## Prioridades para esta sesión nueva

1. **[ ] Corregir AcousticIDClient.swift** — meta=recordings+isrcs, SHA-256 idempotency
2. **[ ] Crear endpoint POST /v1/identify** en el servidor
3. **[ ] Migrar fingerprints.db → PostgreSQL** (tabla tracks del servidor)
4. **[ ] Crear tabla plays** y lógica de registro
5. **[ ] Dashboard admin básico** — HTML simple con stats en tiempo real
6. **[ ] Reporte mensual** — script Python + email

---

## Notas importantes

- La música es mayormente **colombiana**: salsa, vallenato, popular, reguetón → tasa ISRC baja en AcousticID es normal y esperada
- Los fingerprints que se generen localmente son válidos aunque no tengan ISRC aún — se pueden usar para matching interno
- El sistema debe funcionar **offline** en el venue y sincronizar cuando haya internet
- fpcalc debe correr en el device (iOS) — la huella se genera localmente, el lookup al servidor es lo único que necesita red
