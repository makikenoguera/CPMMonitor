# CPM Monitor — Memoria del Proyecto v4.3
**Fecha de hito:** 26 de mayo de 2026  
**Tag Git:** `v4.3-stable`  
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
- **DB:** `/opt/cpmtracks/api/cpmtracks.db`

### Mac (desarrollo)
- **Proyecto:** `/Users/macbookpro/CPMTracks/`
- **App macOS:** `main.py` + `ui/` + `core/`
- **Spec Windows:** `CPMMonitor_win.spec`
- **Installer:** `installer.iss` (Inno Setup)

### Windows (usuario final)
- **Config:** `%APPDATA%\CPMTracks\config.json`
- **DB local:** `%APPDATA%\CPMTracks\cpm_tracks.db`

---

## Stack del agente (Mac + Windows)

```
main.py
├── core/
│   ├── scanner_mac.py / scanner_win.py   ← detecta canción activa
│   ├── sync.py                            ← envía plays al API
│   ├── database.py                        ← cola offline SQLite
│   ├── config.py                          ← carga/guarda config.json
│   ├── updater.py                         ← auto-update desde version.json
│   ├── mensajes.py                        ← push messages del servidor
│   └── autostart.py                       ← inicio automático con el sistema
└── ui/
    ├── tray_mac.py / tray_win.py          ← ícono en barra de tareas
    ├── window.py                          ← panel principal (tabla de canciones)
    ├── setup.py                           ← pantalla de activación/login
    ├── mensaje_ui.py                      ← popup de mensajes push
    └── banner_ui.py                       ← banner flotante
```

---

## API REST — Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/login` | Autenticación, retorna session_token |
| POST | `/v1/plays` | Registrar reproducción |
| GET | `/mensajes` | Mensajes push pendientes |
| POST | `/mensajes/:id/leer` | Marcar mensaje leído |
| GET | `/admin/usuarios` | Listar usuarios (superadmin) |
| POST | `/admin/usuarios` | Crear usuario |
| PUT | `/admin/usuarios/:id` | Editar usuario (nombre, rol, id_local, password) |
| DELETE | `/admin/usuarios/:id` | Eliminar usuario (hard delete) |
| GET | `/admin/locales` | Listar establecimientos |
| POST | `/admin/locales` | Crear establecimiento (ID aleatorio XXXX-XXXX-XXXX) |
| PUT | `/admin/locales/:id` | Editar establecimiento |
| DELETE | `/admin/locales/:id` | Desactivar establecimiento |

---

## Dashboard — Funcionalidades v4.3

### Panel Superadmin
- **Reporte general:** KPIs de ingresos, plays por período, tabla de establecimientos
- **Vista por establecimiento:** plays por canción/artista, ingresos
- **Admin → Establecimientos:** crear, editar, activar/desactivar. Modal muestra usuarios vinculados + dropdown para vincular/desvincular
- **Admin → Usuarios:** tabla con Nombre + Email + Rol + Establecimiento + Estado. Botones Editar y Eliminar por fila. Modal unificado create/edit (password opcional al editar, email no editable)
- **Admin → Mensajes push:** enviar mensaje a uno o todos los establecimientos
- **Admin → Configuración:** % de ingreso por establecimiento

### IDs de establecimientos
Formato aleatorio `XXXX-XXXX-XXXX` (A-Z + 0-9), generado en el servidor. No secuencial, no predecible.

---

## Build Windows

### Proceso
1. Push a tag `v*` en GitHub → dispara `build_windows.yml`
2. GitHub Actions (`windows-latest`) instala dependencias de `requirements_win.txt`
3. PyInstaller con `CPMMonitor_win.spec` → `dist/CPMMonitor/` (onedir, sin UPX)
4. Inno Setup con `installer.iss` → `Output/CPMMonitor_Setup_v4.3.exe`
5. Release automático en GitHub con el `.exe` adjunto

### Decisiones clave
- **onedir** (no onefile): evita extracción en temp → no lo bloquea Windows Defender
- **UPX desactivado**: UPX corrompe las DLLs de Qt5 en Windows
- **`collect_all('PyQt5')`**: incluye todos los datos/binarios de Qt
- **Inno Setup** con `PrivilegesRequired=lowest`: instala en `%LOCALAPPDATA%` sin necesitar admin

---

## Fixes críticos aplicados en v4.3

| Problema | Solución |
|---|---|
| Canciones no se guardaban en Windows | `database.py`: path condicional `%APPDATA%` vs `~/Library/...` |
| DLL Qt no carga en Windows | `upx=False` en spec |
| `ModuleNotFoundError: PyQt5.QtWidgets` | `collect_all('PyQt5')` en spec |
| Menú clic derecho no aparecía | `self._menu = QMenu()` (evitar GC de Python) |
| SSL/certifi error en bundle | Función `_make_ssl()` que busca `sys._MEIPASS` |
| Windows Defender bloquea onefile | Cambio a onedir + Inno Setup |
| `Permission denied` en GitHub Release | `permissions: contents: write` en workflow |

---

## Distribución

- **URL descarga:** `https://monitor.cpmtracks.com/descargar.html`
- **macOS:** `.pkg` + `.zip` en `/opt/cpmtracks/dashboard/monitor-install/`
- **Windows:** `.exe` (instalador Inno Setup) en el mismo directorio
- **Auto-update:** `version.json` en el servidor, el agente compara al iniciar

### version.json actual
```json
{
  "version": "4.3",
  "url": "https://monitor.cpmtracks.com/monitor-install/CPMMonitor_v4.3.zip",
  "url_win_exe": "https://monitor.cpmtracks.com/monitor-install/CPMMonitor.exe",
  "url_win_zip": "https://monitor.cpmtracks.com/monitor-install/CPMMonitor_v4.3_win.zip"
}
```

---

## Credenciales de prueba conocidas
- **Superadmin:** `emilio@cpmtracks.com` / `CPM2025emilio`
- **Establecimiento de prueba:** `Local de Makike` (ID aleatorio asignado)

---

## Pendientes / Próximos pasos sugeridos

- [ ] Confirmar que Windows sync funciona de extremo a extremo (Nelson)
- [ ] Instalar en establecimiento real en Mac (confirmar flujo completo)
- [ ] Agregar campo "activo" toggle en modal de usuario (no solo eliminar)
- [ ] Estadísticas por usuario en dashboard
- [ ] Notificaciones por email al crear usuario nuevo
- [ ] Probar auto-updater en Windows cuando salga v4.4
