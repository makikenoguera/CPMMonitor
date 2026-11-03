import Foundation
import Combine

/// Orquestador principal del sistema ACR (v3.0 — SumarteRed).
/// Monitorea el nivel RMS del audio del sistema y dispara consultas al servidor
/// SumarteRed cuando detecta actividad o cambios en la reproducción.
///
/// Diferencias vs v2.0:
///   • Llama a IdentifyClient (POST /v1/identify en servidor propio) en lugar de AcousticID directo
///   • Threshold de confianza: 0.80 (subido desde 0.65)
///   • Solo registra plays si `inCatalog: true` (canción en catálogo SumarteRed)
///   • Auth via API key del venue (no acoustidApiKey)
class ACRScanner: ObservableObject {
    static let shared = ACRScanner()

    // MARK: - Publicado
    @Published var lastIdentifiedTrack: TrackInfo? = nil
    @Published var isListening = false
    @Published var lastQueryStatus: QueryStatus = .idle

    enum QueryStatus {
        case idle
        case querying
        case matched(String)       // "Artista - Titulo"
        case matchedOutOfCatalog(String)  // identificado pero no en catálogo
        case noMatch
        case noFpcalc
        case notConfigured         // falta venueId o apiKey
    }

    // MARK: - Callbacks
    var onTrackDetected: ((TrackInfo?) -> Void)?

    // MARK: - Config
    private let silenceThreshold: Float  = 0.001   // RMS por debajo = silencio
    private let audioThreshold: Float    = 0.004   // RMS por encima = hay audio
    private let minQueryInterval: Double = 20      // segundos mínimos entre consultas
    private let periodicCheckInterval: Double = 20  // re-consulta periódica cada 20s mientras hay audio
    private let sampleSeconds: Double    = 20      // segundos de audio para fingerprint

    // MARK: - Estado interno
    private var wasPlayingAudio    = false
    private var lastQueryTime      = Date.distantPast
    private var lastQueryTrackId   = ""
    private var isQueryInFlight    = false
    private var pendingAudioQuery: DispatchWorkItem?   // cancelable — evita stacking de asyncAfter
    /// Momento en que se detectó audio por primera vez (tras silencio).
    /// Se usa para pre-acreditar los segundos escuchados antes de la identificación.
    private(set) var audioDetectedAt: Date = .distantPast

    // MARK: - Timers
    private var rmsMonitorTimer:    Timer?
    private var periodicQueryTimer: Timer?

    private let audioCapture = AudioCaptureManager.shared

    private init() {}

    // MARK: - Control
    func start() {
        guard !isListening else { return }

        Task {
            // Ir directo a startCapture() sin checkPermission() previo.
            // SCShareableContent resuelve el permiso internamente:
            //   - Si está concedido: funciona silenciosamente ✅
            //   - Si no está concedido: lanza un error (macOS 14+) o muestra el
            //     diálogo del sistema una sola vez (macOS 13).
            // Llamar checkPermission() antes causaba un segundo diálogo duplicado.
            do {
                try await audioCapture.startCapture()
                await MainActor.run {
                    self.isListening = true
                    self.startTimers()
                    print("[ACR] ✅ Escuchando audio del sistema")
                }
            } catch {
                print("[ACR] Error iniciando captura: \(error)")
                await MainActor.run {
                    // Marcar permiso según tipo de error.
                    // SCKit lanza errores de dominio SCStreamErrorDomain cuando el permiso
                    // está denegado. Cualquier otro error (sin display, etc.) no implica
                    // que el permiso esté denegado — podría ser un problema temporal.
                    let errorStr = error.localizedDescription.lowercased()
                    let isPermissionError = errorStr.contains("permission") ||
                                           errorStr.contains("denied") ||
                                           errorStr.contains("access") ||
                                           (error as NSError).code == -3801  // SCStreamErrorCode.noWindowList
                    if isPermissionError {
                        AudioCaptureManager.shared.permissionStatus = .denied
                        print("[ACR] Permiso denegado — mostrar UI de Reintentar")
                    } else {
                        // Error técnico (sin pantalla, etc.) — no cambiar estado de permiso
                        print("[ACR] Error técnico: \(error) — reintentando en 5s…")
                        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                            guard !self.isListening else { return }
                            self.start()
                        }
                    }
                }
            }
        }
    }

    /// Reinicia desde cero, incluso si un intento anterior quedó en estado inconsistente.
    /// Llamado por AudioCaptureManager.requestPermissionAndStart() tras pedir el permiso.
    func forceRestart() {
        // Cancelar timers y estado previo
        rmsMonitorTimer?.invalidate()
        periodicQueryTimer?.invalidate()
        rmsMonitorTimer = nil
        periodicQueryTimer = nil
        pendingAudioQuery?.cancel()
        pendingAudioQuery = nil
        isListening = false          // reset para que start() no salte el guard
        Task { await audioCapture.stopCapture() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            self.start()
        }
    }

    func stop() {
        rmsMonitorTimer?.invalidate()
        periodicQueryTimer?.invalidate()
        rmsMonitorTimer = nil
        periodicQueryTimer = nil
        pendingAudioQuery?.cancel()
        pendingAudioQuery = nil
        Task { await audioCapture.stopCapture() }
        isListening = false
        lastIdentifiedTrack = nil
        print("[ACR] Detenido")
    }

    // MARK: - Timers internos
    private func startTimers() {
        rmsMonitorTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            self?.checkAudioActivity()
        }
        periodicQueryTimer = Timer.scheduledTimer(withTimeInterval: periodicCheckInterval, repeats: true) { [weak self] _ in
            self?.periodicQuery()
        }
        RunLoop.main.add(rmsMonitorTimer!,    forMode: .common)
        RunLoop.main.add(periodicQueryTimer!, forMode: .common)
    }

    // MARK: - Detección de actividad
    private func checkAudioActivity() {
        let rms = audioCapture.currentRMS
        let playing = rms > audioThreshold

        if playing && !wasPlayingAudio {
            // Nuevo audio detectado tras silencio.
            pendingAudioQuery?.cancel()
            pendingAudioQuery = nil

            // Registrar el momento exacto en que empezó el audio.
            audioDetectedAt = Date()

            // Limpiar buffer: descarta audio previo (ruido del sistema, canción anterior).
            audioCapture.clearBuffer()

            // Programar consulta después de sampleSeconds con un WorkItem cancelable.
            // 10s → muchos falsos positivos en intros genéricas.
            // 20s → fingerprint con ~118 valores (vs 59), mucho más fiable.
            print("[ACR] Audio detectado (RMS: \(String(format: "%.4f", rms))), esperando \(Int(sampleSeconds))s para capturar fingerprint limpio…")
            let work = DispatchWorkItem { [weak self] in
                self?.pendingAudioQuery = nil
                self?.triggerQuery(reason: "audio_started")
            }
            pendingAudioQuery = work
            DispatchQueue.main.asyncAfter(deadline: .now() + sampleSeconds, execute: work)

        } else if !playing && wasPlayingAudio {
            // Silencio: cancelar la consulta pendiente si aún no disparó.
            pendingAudioQuery?.cancel()
            pendingAudioQuery = nil
            print("[ACR] Silencio detectado")
            lastIdentifiedTrack = nil
            lastQueryTrackId    = ""
            onTrackDetected?(nil)
        }

        wasPlayingAudio = playing
    }

    private func periodicQuery() {
        guard audioCapture.currentRMS > audioThreshold else { return }
        let elapsed = Date().timeIntervalSince(lastQueryTime)
        guard elapsed >= periodicCheckInterval else { return }
        triggerQuery(reason: "periodic_\(Int(elapsed))s")
    }

    // MARK: - Consulta ACR (matching local)
    func triggerQuery(reason: String) {
        guard !isQueryInFlight else { return }

        let elapsed = Date().timeIntervalSince(lastQueryTime)
        guard elapsed >= minQueryInterval else { return }

        guard FingerprintEngine.isAvailable else {
            lastQueryStatus = .noFpcalc
            print("[ACR] fpcalc no disponible — instalar: brew install chromaprint")
            return
        }

        let cfg = ConfigManager.shared.config
        guard !cfg.venueId.isEmpty, !cfg.apiKey.isEmpty else {
            lastQueryStatus = .notConfigured
            print("[ACR] Venue no configurado — faltan venueId o apiKey")
            return
        }

        guard LocalMatcher.shared.trackCount > 0 else {
            print("[ACR] Catálogo local vacío — esperando sincronización…")
            lastQueryStatus = .idle
            // Disparar descarga si no está en proceso
            Task { await CatalogManager.shared.checkForUpdates() }
            return
        }

        lastQueryTime   = Date()
        isQueryInFlight = true
        lastQueryStatus = .querying

        print("[ACR] Consultando localmente (razón: \(reason), catálogo: \(LocalMatcher.shared.trackCount) tracks)…")

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }

            // Capturar PCM del buffer circular
            guard let pcmData = self.audioCapture.captureSample(seconds: self.sampleSeconds) else {
                print("[ACR] Buffer insuficiente para fingerprint")
                DispatchQueue.main.async {
                    self.isQueryInFlight = false
                    self.lastQueryStatus = .idle
                }
                return
            }

            // Generar fingerprint raw (int32) — sin red, sin compresión extra
            let captureRate = self.audioCapture.actualSampleRate
            guard let fp = FingerprintEngine.generateRaw(from: pcmData, sampleRate: captureRate) else {
                print("[ACR] Error generando fingerprint")
                DispatchQueue.main.async {
                    self.isQueryInFlight = false
                    self.lastQueryStatus = .noMatch
                }
                return
            }

            print("[ACR] Fingerprint generado: \(fp.values.count) valores, \(fp.duration)s")

            // Matching local — todo en este hilo background
            let result = LocalMatcher.shared.match(query: fp.values)

            DispatchQueue.main.async {
                self.isQueryInFlight = false

                if let result = result {
                    let trackId = "\(result.artista.lowercased())|\(result.titulo.lowercased())"

                    let track = TrackInfo(
                        fuente:         "acr",
                        artista:        result.artista,
                        titulo:         result.titulo,
                        duracionSeg:    result.durationSeg,
                        isrc:           result.isrc,
                        isrcFuente:     result.isrc.isEmpty ? "" : "sumartered",
                        inCatalog:      result.inCatalog,
                        isPromovida:    result.isPromovida,
                        confianza:      Double(result.score),
                        isPlaying:      true,
                        playerPosition: nil
                    )

                    self.lastIdentifiedTrack = track
                    self.lastQueryTrackId    = trackId

                    if result.inCatalog {
                        self.lastQueryStatus = .matched("\(result.artista) - \(result.titulo)")
                    } else {
                        self.lastQueryStatus = .matchedOutOfCatalog("\(result.artista) - \(result.titulo)")
                    }

                    self.onTrackDetected?(track)
                } else {
                    self.lastQueryStatus = .noMatch
                    // Reintentar a los 20s si todavía hay audio y no se ha identificado nada.
                    // El timer periódico (20s) también dispararía, pero este retry lo hace
                    // explícito para el caso de primer fallo antes de que el timer arranque.
                    if self.audioCapture.currentRMS > self.audioThreshold {
                        let work = DispatchWorkItem { [weak self] in
                            guard let self = self,
                                  self.audioCapture.currentRMS > self.audioThreshold,
                                  self.lastIdentifiedTrack == nil else { return }
                            self.triggerQuery(reason: "retry_no_match")
                        }
                        DispatchQueue.main.asyncAfter(deadline: .now() + self.sampleSeconds, execute: work)
                    }
                }
            }
        }
    }
}
