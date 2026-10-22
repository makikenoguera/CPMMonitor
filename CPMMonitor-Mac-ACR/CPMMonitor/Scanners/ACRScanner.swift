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
    private let periodicCheckInterval: Double = 60  // re-consulta forzada cada 60s (música continua)

    // MARK: - Estado interno
    private var wasPlayingAudio  = false
    private var lastQueryTime    = Date.distantPast
    private var lastQueryTrackId = ""
    private var isQueryInFlight  = false

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
                    // Marcar como denegado para que la UI muestre el botón correcto
                    AudioCaptureManager.shared.permissionStatus = .denied
                }
            }
        }
    }

    func stop() {
        rmsMonitorTimer?.invalidate()
        periodicQueryTimer?.invalidate()
        rmsMonitorTimer = nil
        periodicQueryTimer = nil
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
            print("[ACR] Audio detectado (RMS: \(String(format: "%.4f", rms))), consultando en 2s…")
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
                self?.triggerQuery(reason: "audio_started")
            }
        } else if !playing && wasPlayingAudio {
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

    // MARK: - Consulta ACR
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

        lastQueryTime   = Date()
        isQueryInFlight = true
        lastQueryStatus = .querying

        print("[ACR] Consultando (razón: \(reason))…")

        DispatchQueue.global(qos: .background).async { [weak self] in
            guard let self = self else { return }

            guard let pcmData = self.audioCapture.captureSample(seconds: 10) else {
                print("[ACR] Buffer insuficiente para fingerprint")
                DispatchQueue.main.async {
                    self.isQueryInFlight = false
                    self.lastQueryStatus = .idle
                }
                return
            }

            guard let fp = FingerprintEngine.generate(from: pcmData) else {
                print("[ACR] Error generando fingerprint")
                DispatchQueue.main.async {
                    self.isQueryInFlight = false
                    self.lastQueryStatus = .noMatch
                }
                return
            }

            IdentifyClient.lookup(
                fingerprint: fp.value,
                duration:    fp.duration,
                serverURL:   cfg.serverURL,
                venueId:     cfg.venueId,
                apiKey:      cfg.apiKey
            ) { [weak self] result in
                guard let self = self else { return }

                DispatchQueue.main.async {
                    self.isQueryInFlight = false

                    if let result = result {
                        let trackId = "\(result.artista.lowercased())|\(result.titulo.lowercased())"

                        let track = TrackInfo(
                            fuente:         "acr",
                            artista:        result.artista,
                            titulo:         result.titulo,
                            duracionSeg:    Double(result.duracion),
                            isrc:           result.isrc,
                            isrcFuente:     result.isrcFuente,
                            inCatalog:      result.inCatalog,
                            confianza:      result.confianza,
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
                    }
                }
            }
        }
    }
}
