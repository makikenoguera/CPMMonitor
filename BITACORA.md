# CPM Monitor — Bitácora de Desarrollo
**Proyecto:** Sistema de monitoreo de reproducciones musicales para establecimientos comerciales  
**Propósito:** Colombia Play Music (ACPM) — detección de canciones para pago de regalías  
**Fuentes:** archivos de código, git log, documentos MEMORIA_vX.X.md, transcripts de Claude Code, conversaciones claude.ai

---

## 📅 Antes de marzo 9, 2026 — El origen (conversación perdida)

- El proyecto nació con el nombre **"CPM Match"** — no "CPM Monitor"
- La idea fundacional: crear una herramienta que detectara automáticamente qué canciones suenan en un establecimiento comercial, para registrar el play y pagar regalías a los artistas
- Esta conversación original ocurrió en **claude.ai** (versión web), antes de cualquier registro local
- El nombre "Match" hacía referencia a *hacer match* entre el audio que suena y una canción en una base de datos
- **Esta conversación no es recuperable** — no quedó guardada en ningún proyecto de claude.ai

---

## 📅 Marzo 9, 2026 — Primeros activos del proyecto

- Se crean los primeros logos: **"CPM Match"** y **"CPM Tracks"**
  - `logo-cpm-tracks.png` (logo principal del proyecto)
  - `boton-cpm-tracks-mm.png` (variante para botones)
- El proyecto vive en `/Users/macbookpro/MonitorMusical/`
- Identificador de la app: `com.cpmmatch.monitor`
- Nombre interno: **"CPMM Monitor"** (CPM Match Monitor)

---

## 📅 Marzo 22–23, 2026 — Primera versión funcional: CPM Match v2.3.0

- Se tiene la **primera versión que realmente detecta canciones** y las registra
- Tecnología: **Python + PyQt6**, empaquetado como app macOS con `py2app`
- Detecta solo **Spotify** (vía AppleScript — lee el título de la canción activa en el reproductor)
- Base de datos local **SQLite** (`cpmtracks.db`) con tabla `plays`: guarda título, artista, ISRC, duración, segundos escuchados, porcentaje
- Primer modelo de datos: ISRC + título + artista + valor por play en COP
- Comunicación básica con el servidor para enviar los plays registrados

**Primera canción registrada en la historia del proyecto:**  
🎵 *"Historia de Amor"* — Fruto del Madero  
📅 22 de marzo de 2026, 22:54

- En total se registran **37 plays** en esa primera sesión de prueba (Spotify + YouTube)
- `setup.py` de py2app con la configuración del bundle

**Resultado:** Primera versión funcional. CPM Match detecta Spotify en Mac. 37 canciones registradas.

---

## 📅 Mayo 3–4, 2026 — Retoma en claude.ai: "revisa todo el proyecto"

- Se retoma el proyecto con una conversación nueva en claude.ai (proyecto "CPM Match")
- **Primera pregunta de esta etapa:**  
  > *"revisa todo el proyecto y dame el status y el momento en el que estamos"*
- La respuesta de Claude confirma que ya hay un modelo de negocio documentado (valor por play, distribución entre partes), un documento de inversión, y código funcional
- Se crea el ícono `icon.png` para la interfaz gráfica
- Se trabaja en scripts de build para macOS (`build_mac.sh`)

---

## 📅 Mayo 11–13, 2026 — Identidad visual del monitor

- Se crean los íconos definitivos de la app:
  - `icon.icns` (ícono macOS, formato nativo Apple)
  - `icon_tray.png` y `icon_tray.ico` (ícono para bandeja del sistema en Mac y Windows)
- Se define la paleta visual: ecualizador azul + "CPM TRACKS"

---

## 📅 Mayo 25, 2026 — Control de versiones: primer commit en GitHub

- Se formaliza el proyecto con control de versiones: repositorio `makikenoguera/SumarteRedMonitor`
- **Primer commit:** `Initial commit — CPM Monitor v4.3`
- A partir de este punto el desarrollo queda registrado en git

---

## 📅 Mayo 26, 2026 — v4.3: primera versión "seria" y distribuible

- Primera versión empaquetada y distribuible para **macOS y Windows**
- **Panel de administración web** completamente funcional:
  - KPIs de ingresos y plays
  - Gestión de establecimientos y usuarios (crear, editar, activar/desactivar)
  - Mensajes push desde el servidor al monitor
  - Vista de plays por canción/artista
  - Catálogo de obras registradas con ACPM
- **Instalador profesional** con Inno Setup: instala sin pedir permisos de administrador, no bloquea el antivirus
- Se publica en `monitor.cpmtracks.com/descargar.html` con descarga directa
- Se activa **auto-actualización**: el monitor verifica al iniciar si hay versión nueva

**Fixes críticos de esta versión (problemas reales al instalar en Windows):**
- Las canciones no se guardaban en Windows → path condicional `%APPDATA%` vs `~/Library/...`
- DLLs de Qt5 no cargaban → desactivar UPX en el empaquetador (UPX corrompe las DLLs de Qt)
- Windows Defender bloqueaba el instalador onefile → cambio a instalador `onedir` + Inno Setup
- Menú clic derecho no aparecía → prevenir que Python hiciera garbage collection del menú
- SSL/certifi errores en bundle → función especial que busca el certificado dentro del paquete

**Modelo de negocio consolidado:**
- $3.000 COP por play completo (≥90% escuchado)
- Distribuido: $500 bar / $500 Colombia Play Music / $500 CPM-Match / $500 SumarteRed / $1.000 costos
- Establecimientos → contratan ACPM → instalan monitor → reciben parte del recaudo

**Resultado:** Monitor instalable en establecimientos. Detecta Spotify en Mac. Windows en pruebas con Nelson.

---

## 📅 Mayo 27, 2026 — v4.4 → v4.5: más fuentes, más inteligente

- **Múltiples fuentes de audio:** se agrega detección de YouTube (Chrome/Safari), Apple Music y VLC además de Spotify
- **ISRC por MusicBrainz:** integración gratuita para obtener el ISRC de una canción a partir de artista + título — sin pagar API
- **Primera exploración de reconocimiento acústico (ACRCloud):** identificar canciones por el sonido en vez del reproductor
  - Problema: activaba el micrófono constantemente → ícono naranja en macOS → usuarios se asustan
  - Se deja como opción de último recurso (desactivado del scan automático, con throttle de 30s)
- **Porcentaje escuchado:** ahora se envía al servidor cuántos segundos reales se oyó cada canción
- **Umbral de play válido:** una canción cuenta cuando se escucha al menos el **90%**
- **Duración estimada para YouTube:** como YouTube no siempre reporta la duración, se usa 3:30 (210s) como estimado por defecto
- Fix: notificaciones YouTube con prefijo `(206)` se limpiaban del título
- Nuevo logo con ecualizador azul reemplaza el placeholder verde anterior

**Resultado:** Monitor detecta 4 fuentes. ISRC por MusicBrainz. Porcentaje enviado al servidor. Build Windows por GitHub Actions.

---

## 📅 Junio 2026 — Decisión estratégica: reescribir en Swift nativo

- **Decisión:** abandonar Python/PyQt5 y reescribir el monitor completo en **Swift nativo para macOS**
- **Razones:**
  - Python + PyQt5 tiene limitaciones serias en macOS moderno: permisos TCC, integración con el sistema, ícono en el Dock no deseable
  - Swift da acceso real a las APIs de Apple: AppleScript nativo, permisos TCC, barra de menú sin Dock
  - La app debe sentirse como una app de macOS, no como un programa Python
- Se crea el proyecto `SumarteRedMonitor-Mac` en Swift/SwiftUI con XcodeGen
- La versión Python queda archivada como respaldo en `/Users/macbookpro/CPMTracks/`

**Nueva arquitectura modular:**
- `4 scanners independientes:` Spotify, Apple Music, YouTube, VLC — cada uno con su AppleScript
- Base de datos SQLite local con cola offline de plays
- Sincronización automática cada 60 segundos al servidor
- Panel flotante en la **barra de menú** (sin ícono en el Dock)

---

## 📅 Junio 21–27, 2026 — Inicio de Claude Code + trabajo paralelo (certificados)

- Primeros registros en **Claude Code** (primera sesión local del proyecto)
- En paralelo al monitor, se construye el sistema de **Certificados Digitales** para Colombia Play Music:
  - Certificados en PDF para establecimientos que pagan derechos
  - Dashboard con vista por tipo de usuario (con/sin cuenta)
  - Liquidaciones con visor de PDF
  - Firma digital + QR de verificación en los certificados
  - Selector de ciudades colombianas (Bogotá, Chía, etc.) con localidades
  - Versión responsive para móvil
- El monitor Swift sigue desarrollándose en paralelo durante este período

---

## 📅 Junio 30, 2026 — v5.0 Swift: primera versión funcional

- Se documenta el primer hito de la versión Swift en `HANDOFF.md`
- **4 scanners AppleScript** funcionando: Spotify (con posición real), Apple Music (con posición real), YouTube (via JS en Chrome), VLC (sin posición real)
- **Detección de tiempo escuchado por delta de posición:** en vez de contar por intervalos de timer, se calcula cuánto avanzó realmente el reproductor (filtra pausa, adelantar, retroceder)
- **Panel flotante** en barra de menú, sin ícono en Dock (`LSUIElement=YES`)
- **Permisos TCC** para AppleScript: solicita permiso por cada app (Spotify, Apple Music, Chrome, Safari) con diálogo del sistema
- Inicio automático con el sistema (LaunchAgent)
- App distribuida como `.pkg` para instalación limpia

**Issues identificados en v5.0:**
- `launchAtLogin` toggle en UI no funciona realmente
- VLC no tiene posición real de reproducción

---

## 📅 Julio 1–31, 2026 — Mejoras al sistema de certificados

- Se continúa puliendo el sistema de certificados:
  - PDF con fondo a carta completa (problema con compresión horizontal del fondo)
  - Textos con mayúsculas/minúsculas correctas (nombres propios, emails en minúsculas)
  - Texto legal en certificados de SI USUARIOS: *"PAGO POR CONCEPTO DE DERECHOS DE AUTOR Y CONEXOS"*
  - Carga de firma digital en el PDF
  - Logo de Colombia Play Music en el certificado
  - Alineación correcta del QR con respecto al margen izquierdo
  - Sección de certificados generados con listado y visor de PDF

---

## 📅 Agosto 28, 2026 — v5.1 (v1.1.0): versión Swift estable

- Se estabiliza la versión Swift como **v1.1.0** — primera versión "production-ready"
- Documento `MEMORIA_v5.0.md` creado como referencia definitiva de la arquitectura

**Fixes respecto a v5.0:**
- ✅ **launchAtLogin funcional:** implementado con `SMAppService` (macOS 13+) con fallback a LaunchAgent plist (macOS 12)
- ✅ **VLC con posición real:** `VLCScanner.swift` ahora incluye `current time` como `playerPosition`; acumulación por delta real en vez de por timer

**Ecosistema documentado formalmente:**
- CPM Monitor detecta plays → servidor central `monitor.cpmtracks.com`
- SUMARTE Player (reproductor web propio) también reporta al mismo endpoint `POST /v1/plays`
- Ambos usan el mismo `id_local` y formato de datos; se diferencian por el campo `fuente`
- Panel de administración unifica todo

**Marco legal documentado:**
- Sentencia C-509/2004: gestión de derechos no es monopolio de SAYCO/ACINPRO
- Sentencia C-424/2005: coexistencia de modalidades de gestión
- Procuraduría PDET 1608: otros entes pueden cobrar y administrar derechos
- Ley 232/1995: asociaciones legítimas pueden expedir recibos de pago
- ⚠️ Pendiente: licencia de plataforma Spotify y YouTube para uso en locales

- Se hace backup formal de v1.1.0 como versión estable congelada en `SumarteRedMonitor-Mac-v1.1.0-stable/`

**Resultado:** v1.1.0 en producción. Ecosistema ACPM completo documentado.

---

## 📅 Septiembre 13–14, 2026 — Preparación del sistema ACR

- **Decisión estratégica:** explorar reconocimiento acústico real (escuchar los parlantes) como alternativa a los scanners AppleScript
  - Limitación del modelo AppleScript: solo funciona si la música sale de Spotify/Apple Music/YouTube/VLC
  - Si el DJ usa otro software, o el audio viene de otra fuente → el monitor no detecta nada
- Se crea carpeta `SumarteRedMonitor-Mac-ACR` como rama de desarrollo sin tocar v1.1.0
- Se investiga y confirma **ScreenCaptureKit** (disponible desde macOS 13): API oficial de Apple para capturar el audio del sistema sin necesidad de drivers adicionales
- Se confirma que ya no se necesita **BlackHole 2ch** (instalado desde una versión anterior) → se desinstala el driver de audio virtual "CPM Monitor"
- Se instala **fpcalc** (`brew install chromaprint`) — la herramienta que genera huellas acústicas Chromaprint
- Se registra cuenta en **AcousticID** y se obtiene API key gratuita

**Nuevos módulos construidos:**
- `AudioCaptureManager` — captura de audio del sistema con ScreenCaptureKit; buffer circular de 14 segundos; publica nivel RMS en tiempo real
- `FingerprintEngine` — genera huella acústica de los últimos N segundos de audio usando fpcalc
- `AcousticIDClient` — consulta AcousticID con la huella; recibe título, artista, duración, ID de MusicBrainz
- `ACRScanner` — orquestador: detecta audio → espera 2s → consulta AcousticID → re-consulta cada 5 min
- `ScannerManager` reescrito: elimina los 4 scanners AppleScript, acumula tiempo por RMS + reloj del sistema

---

## 📅 Septiembre 15, 2026 — Primera prueba del sistema ACR

- Se compila y ejecuta la versión ACR por primera vez desde Claude Code
- **Errores de compilación resueltos:**
  - Nombre de propiedad de ScreenCaptureKit incorrecto: `excludesCurrentProcessAudio` (no `excludesCurrentProcessAudioFromCapture`)
  - Campos eliminados del modelo de configuración causaban error al leer settings guardados de versiones anteriores → solución: valores por defecto explícitos en cada campo
  - La pantalla de configuración hacía referencia a campos que ya no existen en el modelo

**Problema principal: el permiso de Grabación de pantalla no aparece en macOS 15**
- macOS 14+ ya NO muestra automáticamente el diálogo de "Grabación de pantalla" cuando la app llama a ScreenCaptureKit
- Solución: agregar llamada explícita a `CGRequestScreenCaptureAccess()` cuando falla `SCShareableContent`
- Se agregan botones en la UI: **"Solicitar permiso"** (para estado desconocido) y **"Reintentar"** (para cuando el usuario ya aceptó en Ajustes pero la app aún no lo detectó)
- El usuario acepta el permiso en Ajustes del Sistema → SumarteRedMonitor aparece con toggle azul en Grabación de pantalla

**Estado al cierre de la sesión del 15 de septiembre:**
- ✅ App compilando y corriendo (versión ACR)
- ✅ Permiso de Grabación de pantalla concedido
- ✅ API key de AcousticID configurada
- ✅ fpcalc instalado y funcionando
- ⏳ Pendiente: hacer clic en "Reintentar" para iniciar captura activa
- ❌ Token de sesión vencido → plays se guardan localmente pero no llegan al servidor

---

## 📅 Septiembre 20, 2026 — Fix en sistema de certificados (QR de verificación)

- Se resuelve un problema con el QR de verificación en los certificados generados
- Los usuarios al escanear el QR no podían acceder correctamente a la verificación
- Fix aplicado en el servidor `monitor.cpmtracks.com`

---

## 📅 Octubre 15, 2026 — Sesión de trabajo (transcript disponible)

- Sesión de trabajo registrada en Claude Code
- Detalles de la sesión no completamente recuperables del transcript

---

## 📅 Octubre 17, 2026 — Revisión de arquitectura ACR + esta bitácora

- Se hace una revisión técnica profunda del sistema ACR completo
- **Problema principal identificado: el ISRC que guarda el monitor no es un ISRC real**
  - Se guarda el ID de MusicBrainz (formato UUID) en el campo ISRC
  - El ISRC real tiene formato `CO-ABC-23-00001` y es el identificador oficial para pago de regalías
  - AcousticID puede devolver ISRCs reales si se pide con `meta=recordings+isrcs`
- **Otros problemas identificados:**
  - La `idempotency_key` usa `String.hashValue` de Swift → no determinista entre reinicios de la app → posibles duplicados en el servidor
  - Si AcousticID no devuelve duración de la canción, el play nunca se cuenta aunque se escuchó completa
  - fpcalc no está dentro del bundle de la app → para instalar en otros Macs se necesita Homebrew
  - Token de sesión vencido: `POST /v1/plays` retorna 401 → `/v1/login` retorna 404 (endpoint eliminado del servidor)
  - Umbral de confianza en el reconocimiento (65%) puede ser bajo para pagos de regalías

- **Se busca la primera pregunta del proyecto** en las fuentes disponibles:
  - Transcripts de Claude Code: el más antiguo empieza el 21 de junio de 2026 (trabajando en certificados)
  - Conversación "CPM Monitor" en claude.ai: primera pregunta fue *"revisa todo el proyecto y dame el status y el momento en el que estamos"* (mayo 3, 2026)
  - La pregunta fundacional original (antes de marzo 2026) está en una conversación no recuperable

- **Se crea esta bitácora** como documento histórico del proyecto

---

## 🗺️ Tabla de versiones

| Versión | Fecha | Tecnología | Descripción |
|---------|-------|------------|-------------|
| v2.3.0 (CPM Match) | Mar 22–23, 2026 | Python + PyQt6 | Primer prototipo. Solo Spotify. 37 plays en primera sesión. |
| v4.3 | May 26, 2026 | Python + PyQt5 | Multi-plataforma Mac+Windows. Dashboard web. Instalador Inno Setup. |
| v4.5 | May 27, 2026 | Python + PyQt5 | YouTube/Apple Music/VLC. MusicBrainz ISRC. Porcentaje de escucha. |
| v5.0 | Jun 30, 2026 | Swift nativo | Reescritura completa. 4 scanners AppleScript. Barra de menú. |
| v1.1.0 (v5.1) | Ago 28, 2026 | Swift nativo | Estable. launchAtLogin funcional. VLC con posición real. |
| v2.0 ACR | Sep 13–15, 2026 | Swift + ScreenCaptureKit | Reconocimiento acústico. Sin AppleScript. fpcalc + AcousticID. |

---

## 🔧 Pendientes identificados al día de hoy (Oct 17, 2026)

1. **ISRC real:** cambiar `meta=recordings` por `meta=recordings+isrcs` en AcousticID → extraer ISRC real del response
2. **idempotencyKey determinista:** reemplazar `hashValue` (no determinista) por SHA-256 o concatenación fija
3. **Token vencido:** re-autenticar con el servidor para obtener sesión válida (endpoint `/v1/login` fue eliminado, revisar con el servidor)
4. **Plays sin duración:** guardar el play aunque AcousticID no devuelva duración, usando el tiempo acumulado como proxy
5. **Bundle fpcalc:** incluir `fpcalc` dentro del bundle `.app` para distribución sin dependencia de Homebrew
6. **Umbral de confianza:** subir el umbral de reconocimiento de 65% a 80%+ para mayor precisión en pagos de regalías
7. **Validación contra catálogo ACPM:** solo contar plays de canciones licenciadas en el catálogo propio
8. **Base de datos de huellas propia:** construir fingerprints del catálogo de SumarteRed para no depender de AcousticID

---

*Bitácora generada: 17 de octubre de 2026*  
*Proyecto: CPM Monitor / Colombia Play Music (ACPM)*  
*Fuentes: git log, MEMORIA_v4.3.md, MEMORIA_v4.5.md, MEMORIA_v5.0.md, HANDOFF.md, transcripts Claude Code (jun–oct 2026), conversación claude.ai "CPM Monitor" (may 2026), monitor_v2.py (mar 2026)*
