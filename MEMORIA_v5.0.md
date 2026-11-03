# CPM Monitor — Memoria del Proyecto v5.1
**Fecha:** 2026-08-28
**Estado:** Producción (Swift/SwiftUI, macOS)

---

## 1. ¿Qué es CPM Monitor?

Aplicación nativa para macOS que monitorea la reproducción de música en locales comerciales. Detecta canciones reproducidas en Spotify, Apple Music, YouTube y VLC, calcula el porcentaje escuchado, y reporta los "plays" al servidor central (CPMTracks) para gestión de derechos y pagos a artistas.

La app vive en la barra de menú (sin icono en el Dock) y opera en segundo plano de forma permanente.

**CPM Monitor es el brazo tecnológico de Colombia Play Music (ACPM)** — cumple exactamente lo prometido en el literal #9 y #13 del documento fundacional de la asociación: *"sistemas de monitoreo reales, efectivos y confiables"* e *"identificación en tiempo real de cómo están siendo utilizadas las obras"*.

---

## 1b. Colombia Play Music (ACPM) — El ecosistema completo

### ¿Qué es Colombia Play Music?
Colombia Play Music (ACPM) es una **organización de gestión individual de derechos de autor y conexos** fundada por el usuario de este proyecto. No es una sociedad de gestión colectiva (como SAYCO/ACINPRO), sino una entidad que opera bajo la figura de **gestión individual** amparada en:

- **Sentencia C-509/2004** (Corte Constitucional): confirma que la gestión de derechos no es monopolio de las OSA (organizaciones de gestión colectiva).
- **Sentencia C-424/2005**: reafirma la coexistencia de distintas modalidades de gestión.
- **Procuraduría — Concepto PDET 1608**: la OSA no es exclusiva; otros entes legítimamente constituidos pueden cobrar y administrar derechos.
- **Ley 232/1995**: cualquier asociación de autores legalmente constituida puede expedir recibos de pago por derechos de autor.
- **Ley 1801/2016 (CNPC), Art. 87 num. 5**: los establecimientos deben pagar derechos de autor a quien corresponda.

### Propuesta de valor a establecimientos
> *"Paga tus derechos de autor con Colombia Play Music y recibe dinero por poner música."*

Los establecimientos afiliados:
1. Contratan a ACPM como su gestor de derechos.
2. Instalan CPM Monitor para que la tecnología verifique qué música reproducen.
3. Reciben parte del recaudo distribuido a artistas afiliados (modelo de incentivo).

### Ecosistema tecnológico

```
[Establecimiento]
      │
      ├─► CPM Monitor (macOS)          — detecta plays en Spotify, Apple Music, VLC, YouTube
      │         └─► POST /v1/plays
      │
      ├─► SUMARTE Player (web)         — player propio con YouTube IFrame + tracker.js
      │         └─► POST /v1/plays (fuente: 'SUMARTE_PLAYER')
      │
      └─────────────────────────────────► https://monitor.cpmtracks.com
                                                │
                                         Backend compartido
                                         (mismo endpoint, misma DB de plays)
                                                │
                                         Panel de administración
                                         (gestión de locales, reportes, distribución)
```

**Puntos de integración clave:**
- CPM Monitor y SUMARTE Player envían al **mismo endpoint** (`POST /v1/plays`) con el mismo token de sesión.
- La fuente se diferencia por el campo `fuente` (`"spotify"`, `"vlc"`, `"SUMARTE_PLAYER"`, etc.).
- El mismo `id_local` identifica al establecimiento en ambos sistemas.
- La idempotency_key evita doble conteo si ambos sistemas detectan el mismo play.

### Marco legal para operación del Monitor
| Riesgo | Marco aplicable | Estado |
|--------|-----------------|--------|
| Uso de Spotify en locales | ToS Spotify prohíbe uso comercial sin licencia Premium for Business | ⚠️ Pendiente — ACPM no reemplaza licencia de plataforma |
| Uso de YouTube en locales | ToS YouTube prohíbe en locales sin licencia Content ID / Music for Business | ⚠️ Pendiente — ídem |
| Cobro de derechos de autor | C-509/2004 + PDET 1608 — ACPM puede cobrar legalmente | ✅ Base legal sólida |
| Competencia con SAYCO/ACINPRO | Régimen pluralista — no hay monopolio | ✅ Confirmado por Procuraduría |
| Recibos de pago válidos | Ley 232/1995 — entidades legítimas pueden expedir recibos | ✅ Aplica a ACPM |

**Pregunta abierta crítica:** ¿El Monitor rastrea música de artistas afiliados a ACPM específicamente, o cualquier música reproducida en el local? Esto define si el recaudo es por obras propias o requiere convenio con otras gestoras.

---

## 2. Historial de versiones

| Versión | Tecnología      | Estado      | Notas                                                        |
|---------|-----------------|-------------|--------------------------------------------------------------|
| ≤ 4.5   | Python + PyQt5  | ⚠️ Obsoleto | `main.py`, `core/scanner.py`, instalador `.pkg` PyInstaller  |
| 5.0     | Swift + SwiftUI | ⚠️ Obsoleto | Primera versión Swift; launchAtLogin no funcional, VLC sin posición real |
| **5.1** | **Swift + SwiftUI** | **✅ Activo** | **launchAtLogin funcional (SMAppService + LaunchAgent fallback), VLC con playerPosition real, versión 1.1.0** |

Los archivos de la versión Python siguen en `/Users/macbookpro/CPMTracks/` (no eliminar hasta confirmar migración completa).

---

## 3. Arquitectura v5.0 (Swift)

```
SumarteRedMonitor-Mac/
├── project.yml                     # XcodeGen spec
├── SumarteRedMonitor.xcodeproj/           # Generado por XcodeGen (no editar a mano)
├── SumarteRedMonitor/
│   ├── SumarteRedMonitorApp.swift         # Punto de entrada @main, carga AppDelegate
│   ├── AppDelegate.swift           # Orquestador principal (NSApplicationDelegate)
│   ├── Info.plist                  # NSAppleEventsUsageDescription, LSUIElement=YES
│   ├── SumarteRedMonitor.entitlements     # com.apple.security.automation.apple-events
│   ├── Models/
│   │   ├── AppConfig.swift         # Configuración persistida en UserDefaults (Codable)
│   │   ├── PlayRecord.swift        # PlayRecord (DB) + SongCandidate (en memoria) + APIPlay
│   │   └── TrackInfo.swift         # Modelo devuelto por cada scanner
│   ├── Managers/
│   │   ├── ConfigManager.swift     # ObservableObject; isActivated reactivo
│   │   ├── DatabaseManager.swift   # SQLite3 directo; tabla `plays`
│   │   ├── ScannerManager.swift    # Timer + lógica de candidatos; publica currentCandidate
│   │   ├── SyncManager.swift       # Timer 60s; envía pendientes al servidor
│   │   ├── APIClient.swift         # URLSession; /v1/login y /v1/plays
│   │   └── PermissionManager.swift # TCC AppleEvents; check + request por app
│   ├── Scanners/
│   │   ├── SpotifyScanner.swift    # AppleScript; devuelve posición real
│   │   ├── AppleMusicScanner.swift # AppleScript
│   │   ├── YouTubeScanner.swift    # AppleScript sobre Chrome/Safari; JS para posición
│   │   └── VLCScanner.swift        # AppleScript (sin posición real)
│   ├── UI/
│   │   ├── RootView.swift          # Router reactivo: SetupView ↔ ContentView
│   │   ├── SetupView.swift         # Pantalla de login (primera vez)
│   │   ├── ContentView.swift       # Historial + Configuración + Now Playing
│   │   ├── MenuBarManager.swift    # NSStatusItem con ícono y menú contextual
│   │   └── PanelController.swift   # NSPanel flotante que contiene RootView
│   └── Utilities/
│       └── AppleScriptRunner.swift # run() + runCheckingError() + isRunning()
└── Scripts/
    ├── setup.sh                    # Verifica Xcode/XcodeGen, ejecuta xcodegen generate
    └── build_pkg.sh                # xcodebuild archive → export → pkgbuild
```

---

## 4. Flujo de datos

```
Timer (3s)
   │
   ├─► SpotifyScanner.currentTrack()    → TrackInfo? (artista, titulo, duracion, posicion, isPlaying)
   ├─► AppleMusicScanner.currentTrack()
   ├─► YouTubeScanner.currentTrack()   [solo si enableYouTubeScanner = true]
   └─► VLCScanner.currentTrack()
            │
            ▼
      ScannerManager.process()
            │ mantiene SongCandidate en memoria
            │ acumula segundosAcumulados usando delta de posición real
            │ cuando porcentaje ≥ 90% → savePlay()
            ▼
      DatabaseManager.savePlay()  →  SQLite tabla `plays` (enviado=0)
            │
            ▼ (Timer 60s)
      SyncManager.syncPending()
            │
            ▼
      APIClient.sendPlays()  →  POST https://monitor.cpmtracks.com/v1/plays
            │  Header: X-Session-Token: <token>
            │  Respuesta: {"accepted": [...], "total": N}  HTTP 201
            ▼
      DatabaseManager.markSent()  →  enviado=1
```

---

## 5. Detección de tiempo escuchado

### Filosofía
El tiempo escuchado NO se cuenta por intervalos de timer sino por **delta de posición real** del reproductor:

```swift
let delta = playerPosition - lastPlayerPosition
if delta > 0 && delta <= interval * 2.5 {
    segundosAcumulados += delta
}
```

Esto filtra automáticamente:
- **Pausa**: posición no avanza → delta = 0 → no acumula
- **Seek adelante**: delta >> interval → descartado
- **Seek atrás**: delta < 0 → descartado

### Por fuente
| Fuente       | Posición real | Notas                                             |
|--------------|---------------|---------------------------------------------------|
| Spotify      | ✅ `player position` | AppleScript nativo                          |
| Apple Music  | ✅ `player position` | AppleScript nativo                          |
| YouTube      | ✅ JS `video.currentTime` | Requiere Chrome con JS from Apple Events  |
| YouTube      | ⚠️ Solo título | Fallback cuando JS no está habilitado             |
| VLC          | ❌ Sin posición | Acumula por intervalo de timer                   |

### Criterios de registro
- `segundosAcumulados >= minDetectionTime` (default: 15s)
- `porcentaje >= umbralPorcentaje` (default: 90%)
- `duracionSeg > 0` (se necesita conocer la duración)

---

## 6. API del servidor

**Base URL:** `https://monitor.cpmtracks.com`

### POST /v1/login
```json
// Request
{"id_local": "LOCAL-001", "password": "***"}

// Response 200
{"ok": true, "session_token": "tok_xxx", "nombre_local": "Bar El Ejemplo", "id_local": "LOCAL-001"}
```

### POST /v1/plays
```
Header: X-Session-Token: <session_token>
Header: Content-Type: application/json
```
```json
// Request
{"plays": [{"idempotency_key": "...", "timestamp": "...", "id_local": "...",
            "fuente": "spotify", "contenido": "Artista - Titulo",
            "duracion": "3:42", "isrc": "", "porcentaje": 94.2,
            "segundos_escuchados": 201.5, "duracion_seg": 214.0}]}

// Response 201
{"accepted": ["key1", "key2"], "total": 2}
```

**Nota crítica:** La autenticación usa `X-Session-Token`, NO `Authorization: Bearer`.

---

## 7. Base de datos local

**Ubicación:** `~/Library/Application Support/CPMTracks/cpm_tracks.db`

```sql
CREATE TABLE plays (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key     TEXT UNIQUE NOT NULL,
    timestamp           TEXT NOT NULL,
    id_local            TEXT NOT NULL,
    fuente              TEXT NOT NULL,
    contenido           TEXT NOT NULL,
    duracion            TEXT NOT NULL,
    isrc                TEXT NOT NULL,
    porcentaje          REAL NOT NULL DEFAULT 0,
    segundos_escuchados REAL NOT NULL DEFAULT 0,
    duracion_seg        REAL NOT NULL DEFAULT 0,
    enviado             INTEGER NOT NULL DEFAULT 0,
    intentos            INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL
);
```

- `enviado = 0` → pendiente de sync
- `intentos >= 20` → ya no se reintenta (aumentar si se necesita)
- `idempotency_key` = `{idLocal}_{hash(fuente|artista|titulo)}_{hora_unix/3600}`

---

## 8. Permisos de macOS (TCC)

La app necesita permiso de Automatización para cada app objetivo.

**Bundle ID de la app:** `com.cpmtracks.monitor`

**Cómo funciona:**
1. Al primer arranque, `PermissionManager.requestAllPermissions()` envía un AppleScript benigno a cada app en ejecución.
2. macOS muestra diálogo de permiso la primera vez por cada app.
3. Si el usuario deniega, aparece botón "Abrir Ajustes" en la pestaña Configuración.

**Reset de permisos (debug):**
```bash
tccutil reset AppleEvents com.cpmtracks.monitor
```

**Para YouTube con posición:** el usuario debe activar en Chrome:
`Ver → Opciones para desarrolladores → Permitir JavaScript desde Eventos de Apple`

---

## 8b. LaunchAtLogin (v5.1)

Implementado en `Managers/LaunchAtLoginManager.swift`. No requiere helper bundle ni entitlements adicionales.

| macOS | Mecanismo | Notas |
|-------|-----------|-------|
| 13+ | `SMAppService.mainApp.register()` | API moderna; idempotente |
| 12 | LaunchAgent plist en `~/Library/LaunchAgents/com.cpmtracks.monitor.plist` | Escribe el ejecutable real del bundle |

**Flujo:**
- `AppDelegate.applicationDidFinishLaunching` → `LaunchAtLoginManager.setEnabled(config.launchAtLogin)`
- Toggle en Configuración → llama a `LaunchAtLoginManager.setEnabled(_:)` + actualiza `AppConfig`

**Nota dev:** En builds de Xcode (no instalados en `/Applications`), `SMAppService` lanza un error benign `SMAppService.Error.notAuthorized`. El plist fallback sí funciona en cualquier ubicación.

---

## 9. Configuración de la app

Almacenada en `UserDefaults` bajo la clave `cpm_config` (JSON):

| Clave                | Tipo    | Default                              | Descripción                    |
|----------------------|---------|--------------------------------------|--------------------------------|
| `idLocal`            | String  | ""                                   | ID del establecimiento         |
| `sessionToken`       | String  | ""                                   | Token de sesión del servidor   |
| `nombreLocal`        | String  | ""                                   | Nombre para mostrar en UI      |
| `apiBaseURL`         | String  | "https://monitor.cpmtracks.com"      | URL base de la API             |
| `launchAtLogin`      | Bool    | true                                 | Lanzar al iniciar sesión       |
| `scanInterval`       | Double  | 3.0                                  | Segundos entre scans           |
| `minDetectionTime`   | Double  | 15.0                                 | Mínimo para registrar un play  |
| `umbralPorcentaje`   | Double  | 90.0                                 | % mínimo para "contar"         |
| `enableYouTubeScanner` | Bool  | false                               | Habilitar scanner de YouTube   |

---

## 10. Build e instalación

### Requisitos
- macOS 12+ (desarrollo y target)
- Xcode 14+
- XcodeGen (`brew install xcodegen`)

### Generar proyecto
```bash
cd /Users/macbookpro/CPMTracks/SumarteRedMonitor-Mac
xcodegen generate
```

### Build .app
```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
xcodebuild -project SumarteRedMonitor.xcodeproj \
           -scheme SumarteRedMonitor \
           -configuration Release \
           -archivePath build/SumarteRedMonitor.xcarchive \
           archive

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
xcodebuild -exportArchive \
           -archivePath build/SumarteRedMonitor.xcarchive \
           -exportOptionsPlist ExportOptions.plist \
           -exportPath build/export
```

### Build .pkg
```bash
bash Scripts/build_pkg.sh
# Output: build/SumarteRedMonitor-1.0.0.pkg
```

### Instalar
```bash
sudo installer -pkg build/SumarteRedMonitor-1.0.0.pkg -target /
```

---

## 11. Problemas conocidos y pendientes

| # | Problema | Estado | Notas |
|---|----------|--------|-------|
| 1 | App vieja Python en `/Applications/SumarteRedMonitor.app` | ⚠️ Pendiente | Eliminar con: `sudo rm -rf /Applications/SumarteRedMonitor.app` |
| 2 | YouTube sin posición si Chrome JS no está activado | ⚠️ Limitación | Sin duración → plays de YouTube en modo título no se registran. El usuario debe activar «Ver → Opciones para desarrolladores → Permitir JS desde Eventos de Apple» |
| 3 | App no firmada (unsigned) | ⚠️ Normal | `.pkg` sin Developer ID; Gatekeeper puede bloquearlo. Solución: `xattr -cr /Applications/SumarteRedMonitor.app` o aprobar en Ajustes → Privacidad y seguridad |
| ~~4~~ | ~~`launchAtLogin` toggle no funcional~~ | ✅ **Resuelto en v5.1** | `LaunchAtLoginManager.swift` — `SMAppService` (macOS 13+) + LaunchAgent plist (macOS 12) |
| ~~5~~ | ~~VLC sin posición real~~ | ✅ **Resuelto en v5.1** | `VLCScanner.swift` ahora incluye `current time` como `playerPosition`; acumulación por delta real |

---

## 12. Credenciales y accesos

| Recurso | Dato |
|---------|------|
| Servidor | `monitor.cpmtracks.com` |
| Usuario admin | `LOCAL-001` |
| DB local | `~/Library/Application Support/CPMTracks/cpm_tracks.db` |
| Bundle ID | `com.cpmtracks.monitor` |

---

## 13. Cumplimiento legal y pendientes regulatorios

### Estado actual
| Item | Estado | Notas |
|------|--------|-------|
| Gestión de derechos (ACPM) | ✅ Base sólida | C-509/2004 + PDET 1608 + Ley 232/1995 |
| Monitoreo técnico de plays | ✅ Funcional | CPM Monitor v1.1.0 + SumartePlayer tracker.js |
| Licencia plataforma Spotify | ⚠️ No resuelta | ToS prohíbe uso comercial sin Spotify Premium for Business. El Monitor no reemplaza esto. |
| Licencia plataforma YouTube | ⚠️ No resuelta | ToS prohíbe uso en locales; Content ID aplica a reproductores embebidos. SUMARTE Player usa IFrame API — verificar con YouTube/Google. |
| Certificación de obras monitoreadas | ⚠️ Pendiente | Definir si el Monitor rastrea solo obras de artistas afiliados a ACPM o cualquier obra. |
| Acuerdo con SAYCO/ACINPRO | ⚠️ Pendiente | Si se monitorean obras de su repertorio, puede requerirse convenio o notificación. |

### Recomendaciones
1. **Spotify**: animar a establecimientos a contratar **Spotify Premium for Business** (soundtrap.com/spotify-for-business). ACPM gestiona los derechos de autores; Spotify gestiona los derechos de la plataforma. Son capas distintas.
2. **YouTube**: SUMARTE Player es la alternativa propia — reemplaza YouTube en el local con control total. Si el establecimiento usa YouTube directamente, referir a YouTube Music for Business o licencia de Content ID.
3. **Delimitar repertorio ACPM**: crear campo `afiliado_acpm` en el perfil del artista y filtrar plays reportables vs. plays de referencia.
4. **Contrato tipo con locales**: incluir cláusula que el Monitor es herramienta de verificación de cumplimiento (no de licencia de plataforma).

### Campos sugeridos para versión futura del esquema de plays
```sql
-- Agregar a tabla plays:
ALTER TABLE plays ADD COLUMN afiliado_acpm INTEGER NOT NULL DEFAULT 0;
ALTER TABLE plays ADD COLUMN fuente_licencia TEXT NOT NULL DEFAULT '';
-- afiliado_acpm = 1 si el artista está en repertorio ACPM
-- fuente_licencia: 'spotify_business', 'sumarte_player', 'vlc_local', etc.
```

---

## 14. Archivos Python (versión anterior)

La versión Python sigue en `/Users/macbookpro/CPMTracks/`:
- `main.py` — punto de entrada PyQt5
- `core/scanner.py` — lógica de detección
- `ui/` — interfaz PyQt5
- `MEMORIA_v4.5.md` — documentación de esa versión

**No eliminar** hasta que la versión Swift esté estable en producción en todos los locales.
