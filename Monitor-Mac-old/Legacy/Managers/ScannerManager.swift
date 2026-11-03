import Foundation
import Combine

class ScannerManager: ObservableObject {
    static let shared = ScannerManager()

    // MARK: - Estado publicado
    @Published var currentCandidate: SongCandidate? = nil
    @Published var isScanning: Bool = false

    // MARK: - Dependencias
    private let config = ConfigManager.shared
    private let db     = DatabaseManager.shared

    // MARK: - Timer
    private var timer: Timer?

    private init() {}

    // MARK: - Control
    func start() {
        guard !isScanning else { return }
        isScanning = true
        scheduleTimer()
        print("[Scanner] Iniciado, intervalo: \(config.config.scanInterval)s")
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        isScanning = false
        print("[Scanner] Detenido")
    }

    func restart() {
        stop()
        start()
    }

    // MARK: - Timer interno
    private func scheduleTimer() {
        let interval = config.config.scanInterval
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.scan(interval: interval)
        }
        RunLoop.main.add(timer!, forMode: .common)
    }

    // MARK: - Scan (llamado desde timer en main thread)
    private func scan(interval: Double) {
        let scanCfg = config.config

        let track = SpotifyScanner.currentTrack()
                 ?? AppleMusicScanner.currentTrack()
                 ?? (scanCfg.enableYouTubeScanner ? YouTubeScanner.currentTrack() : nil)
                 ?? VLCScanner.currentTrack()

        process(track: track, interval: interval)
    }

    // MARK: - Lógica de detección
    private func process(track: TrackInfo?, interval: Double) {
        let now = Date()
        let cfg = config.config

        // ── Sin ninguna pista detectada ──────────────────────────────────────
        guard let track = track else {
            if let candidate = currentCandidate {
                finalizeIfEligible(candidate)
            }
            currentCandidate = nil
            return
        }

        // ── Hay una pista (puede estar pausada) ──────────────────────────────
        if var candidate = currentCandidate {
            let sameSong = candidate.fuente == track.fuente
                        && candidate.artista.lowercased() == track.artista.lowercased()
                        && candidate.titulo.lowercased()  == track.titulo.lowercased()

            if sameSong {
                if track.isPlaying {
                    // Acumular tiempo escuchado usando posición real si está disponible
                    candidate.update(at: now, interval: interval,
                                     playerPosition: track.playerPosition)
                    // Actualizar duración si antes era 0 (YouTube la recibe en primera lectura)
                    if candidate.duracionSeg == 0 && track.duracionSeg > 0 {
                        candidate.duracionSeg = track.duracionSeg
                    }
                } else {
                    // Pausado: actualizar posición pero NO acumular tiempo
                    candidate.lastSeen = now
                    candidate.lastPlayerPosition = track.playerPosition
                }
                currentCandidate = candidate

                // ¿Ya alcanzó el umbral? → guardar y reiniciar este candidato
                let superaMinimo   = candidate.segundosAcumulados >= cfg.minDetectionTime
                let superaUmbral   = candidate.porcentaje >= cfg.umbralPorcentaje
                let duracionValida = candidate.duracionSeg > 0

                if duracionValida && superaMinimo && superaUmbral {
                    savePlay(candidate)
                    currentCandidate = nil
                }

            } else {
                // Cambió la canción → finalizar anterior, empezar nueva
                finalizeIfEligible(candidate)
                currentCandidate = makeCandidato(from: track, at: now)
            }

        } else {
            // Sin candidato previo → iniciar uno nuevo
            currentCandidate = makeCandidato(from: track, at: now)
        }
    }

    // MARK: - Helpers
    private func makeCandidato(from track: TrackInfo, at date: Date) -> SongCandidate {
        SongCandidate(
            fuente:              track.fuente,
            artista:             track.artista,
            titulo:              track.titulo,
            duracionSeg:         track.duracionSeg,
            isrc:                track.isrc,
            firstSeen:           date,
            lastSeen:            date,
            segundosAcumulados:  0,
            lastPlayerPosition:  track.playerPosition
        )
    }

    private func finalizeIfEligible(_ candidate: SongCandidate) {
        let cfg = config.config
        guard candidate.duracionSeg > 0,
              candidate.segundosAcumulados >= cfg.minDetectionTime,
              candidate.porcentaje >= cfg.umbralPorcentaje else { return }
        savePlay(candidate)
    }

    private func savePlay(_ candidate: SongCandidate) {
        let cfg    = config.config
        let isoFmt = ISO8601DateFormatter()
        let now    = Date()

        var record = PlayRecord()
        record.idempotencyKey     = candidate.idempotencyKey(idLocal: cfg.idLocal)
        record.timestamp          = isoFmt.string(from: now)
        record.idLocal            = cfg.idLocal
        record.fuente             = candidate.fuente
        record.contenido          = candidate.contenido
        record.artista            = candidate.artista
        record.titulo             = candidate.titulo
        record.duracion           = candidate.duracionFormatted
        record.isrc               = candidate.isrc
        record.porcentaje         = candidate.porcentaje
        record.segundosEscuchados = candidate.segundosAcumulados
        record.duracionSeg        = candidate.duracionSeg
        record.createdAt          = now.timeIntervalSince1970

        if db.savePlay(record) {
            print("[Scanner] ✅ Play guardado: \(candidate.contenido) — \(String(format: "%.0f", candidate.porcentaje))% escuchado")
        }
    }
}
