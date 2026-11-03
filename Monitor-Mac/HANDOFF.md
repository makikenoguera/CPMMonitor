# CPM Monitor — Handoff de Desarrollo
**Proyecto:** SumarteRedMonitor-Mac (Swift/SwiftUI)
**Última actualización:** 2026-06-30
**Estado:** Funcional en producción local

---

## Inicio rápido

```bash
# 1. Clonar / abrir el proyecto
cd /Users/macbookpro/CPMTracks/SumarteRedMonitor-Mac

# 2. Generar el proyecto Xcode
xcodegen generate

# 3. Abrir en Xcode
open SumarteRedMonitor.xcodeproj

# 4. Run → Product → Run (Cmd+R)
```

La app aparece en la barra de menú (sin icono en el Dock). Si ya hay configuración guardada inicia directamente en modo monitor; si no, muestra la pantalla de login.

---

## Mapa de archivos

### Punto de entrada
| Archivo | Qué hace |
|---------|----------|
| `SumarteRedMonitor/SumarteRedMonitorApp.swift` | `@main`; conecta el `AppDelegate` con SwiftUI |
| `SumarteRedMonitor/AppDelegate.swift` | Orquestador; inicializa DB, menú, scanner, sync, permisos |

### Modelos
| Archivo | Qué hace |
|---------|----------|
| `Models/AppConfig.swift` | Struct `Codable` con toda la configuración; persistida en `UserDefaults` |
| `Models/TrackInfo.swift` | Modelo temporal que devuelve cada scanner (`fuente`, `titulo`, `artista`, `duracionSeg`, `isPlaying`, `playerPosition`) |
| `Models/PlayRecord.swift` | Tres tipos: `PlayRecord` (fila de DB), `SongCandidate` (tracking en memoria), `APIPlay` (payload para el servidor) |

### Managers (singletons `ObservableObject`)
| Archivo | Qué hace |
|---------|----------|
| `Managers/ConfigManager.swift` | Lee/escribe `AppConfig` en `UserDefaults`; `isActivated` es `Bool` reactivo |
| `Managers/DatabaseManager.swift` | SQLite3 (C API); `savePlay`, `fetchPending`, `fetchHistory`, `markSent`, `countPending` |
| `Managers/ScannerManager.swift` | Timer 3s; llama a los 4 scanners en orden; mantiene `SongCandidate` en memoria; publica `currentCandidate` |
| `Managers/SyncManager.swift` | Timer 60s; recoge pendientes de DB y llama `APIClient.sendPlays` |
| `Managers/APIClient.swift` | `URLSession`; POST `/v1/login` y POST `/v1/plays`; auth con `X-Session-Token` |
| `Managers/PermissionManager.swift` | Verifica y solicita permisos TCC AppleEvents para Spotify, Apple Music, Chrome, Safari |

### Scanners (structs con método estático `currentTrack() -> TrackInfo?`)
| Archivo | Fuente | Posición real |
|---------|--------|---------------|
| `Scanners/SpotifyScanner.swift` | Spotify | ✅ `player position` |
| `Scanners/AppleMusicScanner.swift` | Apple Music | ✅ `player position` |
| `Scanners/YouTubeScanner.swift` | Chrome + Safari | ✅ JS (si está habilitado) / ⚠️ solo título |
| `Scanners/VLCScanner.swift` | VLC | ❌ (usa intervalo de timer) |

### UI
| Archivo | Qué hace |
|---------|----------|
| `UI/RootView.swift` | Router: observa `ConfigManager.isActivated` → muestra `SetupView` o `ContentView` |
| `UI/SetupView.swift` | Pantalla de login; llama `APIClient.login` → guarda config → llama `AppDelegate.didActivate()` |
| `UI/ContentView.swift` | Panel principal: Now Playing + Historial + Configuración (tabs) |
| `UI/MenuBarManager.swift` | `NSStatusItem` con ícono y menú contextual (Abrir / Quit) |
| `UI/PanelController.swift` | `NSPanel` flotante que contiene `RootView`; se abre al clic en el ícono de menú |

### Utilidades
| Archivo | Qué hace |
|---------|----------|
| `Utilities/AppleScriptRunner.swift` | `run(_ script:)` → `String?`; `runCheckingError()` → detecta error -1743/-10003; `isRunning(_ appName:)` |

---

## Flujo de activación (primera vez)

```
Usuario abre panel
    → SetupView visible (config.isActivated = false)
    → Ingresa LOCAL-001 + contraseña
    → APIClient.login() → POST /v1/login
    → Éxito: config.idLocal, config.sessionToken, config.nombreLocal se guardan
    → ConfigManager.save() → UserDefaults
    → AppDelegate.didActivate() llamado
        → ScannerManager.start()
        → SyncManager.start()
        → MenuBarManager.updateStatus(.connected)
    → ConfigManager.isActivated = true
    → RootView observa el cambio → muestra ContentView automáticamente
```

---

## Flujo de detección de plays

```
ScannerManager.scan() (cada 3s)
    │
    ├── SpotifyScanner.currentTrack()    ← primero
    ├── AppleMusicScanner.currentTrack() ← si Spotify = nil
    ├── YouTubeScanner.currentTrack()    ← si enableYouTubeScanner = true
    └── VLCScanner.currentTrack()        ← último fallback
    │
    └── TrackInfo? → process(track:interval:)
            │
            ├── Si track == nil: finalizar candidato actual (si cumple umbral)
            ├── Si misma canción + isPlaying: candidate.update() → acumula delta de posición
            ├── Si misma canción + pausado: actualiza posición pero NO acumula
            ├── Si canción distinta: finalizar anterior, crear candidato nuevo
            └── Si porcentaje >= 90% + duracion > 0 + segundos >= 15: savePlay()

savePlay() → DatabaseManager.savePlay() → tabla plays (enviado=0)

SyncManager.syncPending() (cada 60s)
    └── APIClient.sendPlays() → POST /v1/plays (X-Session-Token)
        └── Respuesta 201 → markSent() para todos los enviados
```

---

## Puntos críticos que queman tiempo si no se conocen

### 1. Header de autenticación
```swift
// ✅ CORRECTO
req.setValue(token, forHTTPHeaderField: "X-Session-Token")

// ❌ INCORRECTO (el servidor lo rechaza silenciosamente)
req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
```

### 2. SQLITE_TRANSIENT no existe en Swift
```swift
// Definir al top del archivo:
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
```

### 3. RootView es el router; no usar rebuild()
`PanelController` siempre carga `RootView()`. Cuando el usuario activa/cierra sesión, `ConfigManager.isActivated` cambia y SwiftUI actualiza la vista automáticamente. No es necesario (ni correcto) llamar `panelController?.rebuild()` desde `SetupView`.

### 4. AppKit es necesario en SetupView
```swift
import AppKit  // ← CRÍTICO para acceder a NSApp.delegate
// Sin este import, NSApp.delegate siempre es nil aunque el delegado exista
```

### 5. YouTube requiere JS habilitado en Chrome
Chrome debe tener activado: `Ver → Opciones para desarrolladores → Permitir JavaScript desde Eventos de Apple`
Sin esto, `execute t javascript "..."` falla con error de AppleScript y el scanner cae al modo de solo-título.

### 6. Permisos TCC / AppleScript
macOS bloquea todos los AppleScripts hasta que el usuario apruebe manualmente (diálogo del sistema). Si los diálogos no aparecen:
```bash
# Resetear permisos para forzar re-solicitud:
tccutil reset AppleEvents com.cpmtracks.monitor
# Luego reiniciar la app
```

### 7. Deployment target macOS 12
- NO usar `LabeledContent` (macOS 13+)
- NO usar `formStyle(.grouped)` (macOS 13+)
- Usar `.cornerRadius()` en lugar de `.clipShape(.rect(cornerRadius:))` para compatibilidad

### 8. XcodeGen debe re-ejecutarse al agregar archivos
Al crear un nuevo `.swift` en el filesystem, hacer:
```bash
xcodegen generate
```
Si no, Xcode no lo compila y el tipo "no existe" aunque el archivo sí esté.

---

## API del servidor

**Base URL:** `https://monitor.cpmtracks.com`

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `/v1/login` | POST | Ninguna | Login con id_local + password |
| `/v1/plays` | POST | X-Session-Token | Enviar plays detectados |

### Request /v1/login
```json
{"id_local": "LOCAL-001", "password": "cpm2024admin"}
```
### Response /v1/login (200)
```json
{"ok": true, "session_token": "tok_...", "nombre_local": "Bar Ejemplo", "id_local": "LOCAL-001"}
```

### Request /v1/plays
```json
{
  "plays": [{
    "idempotency_key": "LOCAL-001_1234567890_473829",
    "timestamp": "2026-06-30T15:30:00Z",
    "id_local": "LOCAL-001",
    "fuente": "spotify",
    "contenido": "Bad Bunny - Tití Me Preguntó",
    "duracion": "4:02",
    "isrc": "",
    "porcentaje": 94.5,
    "segundos_escuchados": 228.7,
    "duracion_seg": 242.0
  }]
}
```
### Response /v1/plays (201)
```json
{"accepted": ["LOCAL-001_1234567890_473829"], "total": 1}
```

---

## Base de datos local

**Path:** `~/Library/Application Support/CPMTracks/cpm_tracks.db`

```sql
-- Ver plays pendientes
SELECT id, contenido, porcentaje, intentos FROM plays WHERE enviado=0;

-- Resetear intentos de plays con buen porcentaje atascados
UPDATE plays SET intentos=0 WHERE enviado=0 AND porcentaje >= 90;

-- Marcar plays basura como enviados
UPDATE plays SET enviado=1 WHERE enviado=0 AND porcentaje < 10;

-- Contar pendientes
SELECT COUNT(*) FROM plays WHERE enviado=0;
```

---

## Build y distribución

### Desarrollo (Xcode)
```bash
xcodegen generate
open SumarteRedMonitor.xcodeproj
# Cmd+R para correr
```

### Build release
```bash
cd /Users/macbookpro/CPMTracks/SumarteRedMonitor-Mac
bash Scripts/build_pkg.sh
# Output: build/SumarteRedMonitor-1.0.0.pkg
```

### Instalar en esta máquina
```bash
sudo installer -pkg build/SumarteRedMonitor-1.0.0.pkg -target /
```

### Desinstalar
```bash
sudo rm -rf /Applications/SumarteRedMonitor.app
# Opcional: limpiar preferencias y DB
defaults delete com.cpmtracks.monitor
rm -rf ~/Library/Application\ Support/CPMTracks/
```

---

## Issues conocidos

### Bug: launchAtLogin toggle no funciona
El toggle está en la UI pero no llama a `SMLoginItemSetEnabled`. Para implementarlo:
```swift
import ServiceManagement
SMLoginItemSetEnabled("com.cpmtracks.monitor-helper" as CFString, enabled)
// O en macOS 13+:
SMAppService.mainApp.register()
```

### Limitación: VLC sin posición real
VLC devuelve solo si está reproduciendo y el título, no la posición. `SongCandidate.update()` detecta `playerPosition == nil` y acumula por intervalo de timer, lo que hace que pausa/seek no se detecten.

### App vieja Python
`/Applications/SumarteRedMonitor.localized/` contiene la versión Python. Puede confundir al usuario si ejecuta esa en lugar de la nueva. Eliminar con:
```bash
sudo rm -rf /Applications/SumarteRedMonitor.localized/
```

### YouTube sin porcentaje real (Chrome JS desactivado)
Si el usuario no activa `Permitir JavaScript desde Eventos de Apple` en Chrome, el scanner detecta la canción pero `porcentaje` siempre acumula por intervalo de timer (igual que VLC). Funcional pero menos preciso.

---

## Próximos pasos sugeridos

1. **Firmado de código**: obtener Apple Developer ID y firmar el `.app` + `.pkg` para eliminar advertencias de Gatekeeper
2. **Notarización**: subir el `.pkg` firmado a Apple para notarización automática
3. **launchAtLogin real**: implementar `SMAppService` (macOS 13+) o `SMLoginItemSetEnabled` (12)
4. **VLC posición real**: usar `tell application "VLC" to time elapsed` o la API HTTP de VLC (`http://localhost:8080/requests/status.json`)
5. **Auto-update**: integrar Sparkle framework para actualizaciones automáticas
6. **Logs persistentes**: escribir `print()` a archivo de log en `~/Library/Logs/CPMTracks/`
7. **Widget de estado**: mostrar estadísticas del día en el menú contextual del ícono
