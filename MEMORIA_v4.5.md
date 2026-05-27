# CPM Monitor — Memoria del Proyecto v4.5
**Fecha de hito:** 27 de mayo de 2026  
**Tag Git:** `v4.5-stable`  
**Repo:** `makikenoguera/CPMMonitor`

---

## ¿Qué es CPM Monitor?
Agente de monitoreo de reproducciones de audio y video para establecimientos comerciales (bares, restaurantes, peluquerías, etc.). Se instala en la barra de tareas (macOS y Windows) y detecta automáticamente las canciones reproducidas, registrándolas en un servidor central para gestión de derechos CPM.

---

## Arquitectura general

| Componente | Tecnología | Ubicación |
|---|---|---|
| Agente de escritorio | Python 3.11 + PyQt5 | Mac / Windows |
| API REST | Flask + SQLite | VPS Hostinger `srv475804` |
| Dashboard web | HTML/CSS/JS vanilla | `/opt/cpmtracks/dashboard/` |
| Página de descarga | HTML estático | `monitor.cpmtracks.com/descargar.html` |
| Build Windows | GitHub Actions | `makikenoguera/CPMMonitor` |

---

## Rutas clave

### VPS
- **API:** `/opt/cpmtracks/api/app.py` — Flask, puerto interno, proxy Nginx
- **Dashboard:** `/opt/cpmtracks/dashboard/index.html`
- **Descarga:** `/opt/cpmtracks/dashboard/descargar.html`
- **DB real:** `/opt/cpmtracks/data/plays.db` ← ojo: NO es `api/cpmtracks.db`

### Mac (desarrollo)
- **Proyecto:** `/Users/macbookpro/CPMTracks/`
- **App macOS:** `main.py` + `ui/` + `core/`
- **Spec macOS:** `CPMMonitor.spec`
- **Spec Windows:** `CPMMonitor_win.spec`
- **Installer:** `installer.iss` (Inno Setup)
- **Logo:** `logo.png` (450×100, ecualizador azul + "CPM TRACKS")

### Windows (usuario final)
- **Config:** `%APPDATA%\CPMTracks\config.json`
- **DB local:** `%APPDATA%\CPMTracks\cpm_tracks.db`

### Mac (usuario final)
- **Config:** `~/Library/Application Support/CPMTracks/config.json`
- **DB local:** `~/Library/Application Support/CPMTracks/cpm_tracks.db`
- **Logs:** `~/Library/Logs/CPMTracks/agent_error.log`

---

## Stack del agente (Mac + Windows)

```
main.py
├── core/
│   ├── scanner.py          ← Mac: detecta Spotify/AppleMusic/YouTube/VLC/QT
│   ├── scanner_win.py      ← Windows: detecta Spotify/YouTube/WASAPI
│   ├── musicbrainz_api.py  ← ISRC por artista+título (sin auth, caché)
│   ├── acrcloud_api.py     ← fingerprint acústico (solo uso manual)
│   ├── audio_capture.py    ← BlackHole (Mac) / WASAPI (Win) / mic fallback
│   ├── sync.py             ← envía plays al API (porcentaje incluido v4.5)
│   ├── database.py         ← cola offline SQLite
│   ├── config.py           ← carga/guarda config.json
│   ├── updater.py          ← auto-update desde version.json
│   ├── mensajes.py         ← push messages del servidor
│   └── autostart.py        ← inicio automático con el sistema
└── ui/
    ├── menu_bar.py         ← ícono barra menú macOS (rumps)
    ├── tray_win.py         ← bandeja sistema Windows
    ├── window.py           ← panel principal (tabla de canciones)
    ├── setup.py            ← pantalla de activación/login
    ├── mensaje_ui.py       ← popup de mensajes push
    └── banner_ui.py        ← banner flotante
```

---

## Scanner — Estrategia sin micrófono (v4.5)

| Fuente | Método | ISRC |
|---|---|---|
| Spotify | AppleScript directo | MusicBrainz por artista+título |
| Apple Music | AppleScript directo | Del campo comentario del track |
| YouTube (Chrome) | Título de pestaña → parse "Artista - Título" | MusicBrainz (caché) |
| YouTube (Safari) | Ídem | MusicBrainz (caché) |
| QuickTime / VLC | Nombre del archivo | "LOCAL" |
| ACRCloud | **Desactivado del scan automático** — solo función manual | — |

**Reglas del scanner:**
- Mínimo **15 segundos** de detección continua antes de guardar un play
- Prefijos de notificación `(206)` se limpian del título YouTube
- Sufijos `(Official Video)`, `[Lyric Video]`, etc. se eliminan

---

## API REST — Endpoints completos (v4.5)

### Autenticación
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/login` | Login usuario, retorna session_token |
| POST | `/auth/logout` | Invalida sesión |
| GET | `/auth/me` | Info del usuario autenticado |
| POST | `/auth/cambiar_clave` | Cambiar contraseña |

### Plays
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/v1/plays` | Recibir plays + cruzar ISRC con catalogo_cpm |
| GET | `/v1/plays/list` | Listar plays por establecimiento |

### Admin (rol superadmin / admin)
| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/admin/usuarios` | Listar / crear usuarios |
| PUT/DELETE | `/admin/usuarios/:id` | Editar / eliminar usuario |
| GET/POST | `/admin/locales` | Listar / crear establecimientos |
| PUT/DELETE | `/admin/locales/:id` | Editar / desactivar establecimiento |
| GET/POST | `/admin/catalogo` | Listar / agregar canción CPM |
| PUT/DELETE | `/admin/catalogo/:id` | Editar estado / eliminar canción |
| GET/POST | `/admin/mensajes` | Mensajes push |
| DELETE | `/admin/mensajes/:id` | Eliminar mensaje |
| GET | `/admin/stats` | KPIs generales |

---

## Base de datos VPS — Tablas principales

### `plays`
```sql
id, idempotency_key, timestamp, id_local, fuente, contenido, duracion,
isrc, duracion_seg, segundos_escuchados, porcentaje, cuenta_pago,
es_cpm INTEGER DEFAULT 0,      ← v4.5: marcado si ISRC está en catálogo
valor_cpm INTEGER DEFAULT 0,   ← v4.5: valor_establecimiento del catálogo
ip_origen, created_at, enviado
```

### `catalogo_cpm`
```sql
id, isrc, artista, titulo, pvp, valor_establecimiento, activo, created_at
```

### `locales`
```sql
id_local, nombre, tipo, activo, token, id_usuario, ultimo_ping, created_at
```

---

## Modelo de negocio CPM (v4.5)

- **PVP artista:** $3.000 COP por play completo (≥90%)
- **Establecimiento recibe:** $500 COP por play CPM (16.67%)
- **CPM retiene:** $2.500 COP por play (83.33%)
- **Paquetes:** 1.000 plays = $3.000.000 COP
- **Match:** ISRC del play vs `catalogo_cpm.isrc` → `es_cpm=1`, `valor_cpm=500`
- **Sin match:** play estadístico, sin ingreso

---

## Build Windows — GitHub Actions

### Proceso automático
1. Push a tag `v4.5` en GitHub → dispara `build_windows.yml`
2. `windows-latest` instala dependencias de `requirements_win.txt`
3. PyInstaller con `CPMMonitor_win.spec` → `dist/CPMMonitor/` (onedir)
4. Inno Setup con `installer.iss` → `Output/CPMMonitor_Setup_v4.5.exe`
5. Release automático en GitHub con el `.exe` adjunto

### Comando para lanzar build
```bash
git tag v4.5 && git push origin v4.5
```

### Decisiones clave
- **onedir** (no onefile): evita extracción en temp → no lo bloquea Defender
- **UPX desactivado**: corrompe DLLs de Qt5
- **`collect_all('PyQt5')`**: incluye todos los datos/binarios de Qt
- **Inno Setup** `PrivilegesRequired=lowest`: instala en `%LOCALAPPDATA%` sin admin

---

## Distribución

- **URL descarga:** `https://monitor.cpmtracks.com/descargar.html`
- **macOS:** `.pkg` + `.zip` en `/opt/cpmtracks/dashboard/monitor-install/`
- **Windows:** `.exe` (instalador Inno Setup) — GitHub Releases
- **Auto-update:** `version.json` en el servidor

### version.json — actualizar a v4.5
```json
{
  "version": "4.5",
  "url": "https://monitor.cpmtracks.com/monitor-install/CPMMonitor_v4.5.zip",
  "url_win_exe": "https://github.com/makikenoguera/CPMMonitor/releases/download/v4.5/CPMMonitor_Setup_v4.5.exe",
  "url_win_zip": "https://monitor.cpmtracks.com/monitor-install/CPMMonitor_v4.5_win.zip"
}
```

---

## Credenciales y accesos

| Servicio | Dato |
|---|---|
| VPS SSH | `root@srv475804` (Hostinger) |
| API URL | `https://monitor.cpmtracks.com` |
| Dashboard | `https://monitor.cpmtracks.com/dashboard/` |
| Superadmin | `emilio@cpmtracks.com` / `CPM2025emilio` |
| GitHub repo | `makikenoguera/CPMMonitor` |
| AcoustID key | `geke6RgPjc` |

---

## Pendientes prioritarios

- [ ] **Task 26** — KPIs plays CPM vs estadístico en dashboard (ingresos separados)
- [ ] **Task 18** — Confirmar sync Windows con Nelson (E2E)
- [ ] **Task 20** — SSL verification (reemplazar CERT_NONE con certifi)
- [ ] **Task 27** — Vista pública catálogo para establecimientos
- [ ] **Task 28** — Sistema de paquetes 1.000 plays
- [ ] Actualizar `version.json` a v4.5 en VPS
- [ ] Generar tag `v4.5` en GitHub para trigger build Windows
- [ ] Actualizar `descargar.html` con link al nuevo instalador

---

## Fixes aplicados en v4.5

| Problema | Solución |
|---|---|
| Catálogo no mostraba canciones | `loadAdminCatalogo()` en `loadAdmin()` + fix key JSON |
| API devuelve array directo (no `{canciones:[]}`) | `Array.isArray(d)?d:(d.canciones\|\|[])` |
| VPS caché GitHub CDN | Usar `urllib` en vez de `wget` para actualizar dashboard |
| Ícono naranja micrófono en macOS | ACRCloud removido del scan automático |
| YouTube `(206) Título` | `re.sub(r'^\(\d+\)\s*', '', titulo)` |
| Plays repetidos al scrollear YouTube | Mínimo 15s antes de guardar play |
| Panel/mensajes no abrían desde menú | Instance lock excluye `--panel`/`--mensajes`/`--banner` |
| % reproducido siempre 0% | Sync ahora envía `porcentaje` + `segundos_escuchados` |
| YouTube sin % (duración desconocida) | Duración estimada 3:30 = 210s para calcular % |
| Logo verde placeholder | Nuevo PNG con ecualizador azul + "CPM TRACKS" |
| Se Paga siempre = No | VPS cruza ISRC con `catalogo_cpm` → `es_cpm=1` |
