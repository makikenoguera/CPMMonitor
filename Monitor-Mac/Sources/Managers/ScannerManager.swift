import Foundation
import Combine

/// Recibe eventos de ACRScanner y gestiona SongCandidate en memoria.
/// Acumula tiempo de escucha usando el reloj del sistema mientras el RMS indica
/// que hay audio reproduciéndose.
///
/// v3.1: Doble confirmación requerida para TODA detección (primera y cambios).
/// Canciones fuera del catálogo producen resultados aleatorios en cada query;
/// una canción real siempre devuelve el mismo resultado dos veces seguidas.
class ScannerManager: ObservableObject {
    static let shared = ScannerManager()

    // MARK: - Publicado
    @Published var currentCandidate: SongCandidate? = nil
    @Published var isScanning: Bool = false

    // MARK: - Dependencias
    private let config = ConfigManager.shared
    private let db     = DatabaseManager.shared
    private let acr    = ACRScanner.shared

    // MARK: - Timer de acumulación
    private var accumulationTimer: Timer?
    private let accumulationInterval: Double = 2.0
    private let audioThreshold: Float = 0.004

    // MARK: - Confirmación de detección
    /// Toda detección (primera O cambio) requiere ≥2 resultados consecutivos idénticos
    /// antes de crear/cambiar el candidato activo.
    ///
    /// Falso positivo: query 1=Anuel, query 2=PSY, query 3=Celia → nunca el mismo → ignorado
    /// Match real:     query 1=Salsa X, query 2=Salsa X → confirmado → candidato creado
    private var pendingTrack: TrackInfo? = nil
    private var pendingCount: Int = 0
    private let requiredConfirmations = 2

    private init() {}

    // MARK: - Control
    func start() {
        guard !isScanning else { return }
        isScanning = true

        acr.onTrackDetected = { [weak self] track in
            self?.handleACREvent(track)
        }
        acr.start()

        print("[Scanner] Iniciado en modo ACR")
    }

    func stop() {
        acr.stop()
        stopAccumulation()
        resetPending()
        isScanning = false
        print("[Scanner] Detenido")
    }

    // MARK: - Reset estado pendiente
    private func resetPending() {
        pendingTrack = nil
        pendingCount = 0
    }

    // MARK: - Manejo de eventos ACR
    private func handleACREvent(_ track: TrackInfo?) {
        guard let track = track else {
            // Silencio detectado: finalizar candidato activo y limpiar todo
            if let candidate = currentCandidate {
                finalizeIfEligible(candidate)
            }
            currentCandidate = nil
            resetPending()
            stopAccumulation()
            return
        }

        if let candidate = currentCandidate {
            // ── Hay candidato activo ──────────────────────────────────────────
            let sameSong = candidate.artista.lowercased() == track.artista.lowercased()
                        && candidate.titulo.lowercased()  == track.titulo.lowercased()

            if sameSong {
                // Confirmación del candidato activo → resetear pendiente y actualizar duración
                resetPending()
                var updated = candidate
                if updated.duracionSeg == 0 && track.duracionSeg > 0 {
                    updated.duracionSeg = track.duracionSeg
                }
                currentCandidate = updated
            } else {
                // Canción diferente: acumular confirmaciones antes de cambiar
                accumulatePending(track) { [weak self] confirmed in
                    guard let self = self else { return }
                    // Solo cambiar si se confirma con alta confianza o varias veces
                    let highConfidence = confirmed.confianza >= 0.88
                    if self.pendingCount >= self.requiredConfirmations || highConfidence {
                        print("[Scanner] Cambio confirmado (\(self.pendingCount)x conf=\(String(format: "%.3f", confirmed.confianza))): \(confirmed.artista) - \(confirmed.titulo)")
                        self.finalizeIfEligible(candidate)
                        self.startNewCandidate(from: confirmed)
                        self.resetPending()
                    } else {
                        print("[Scanner] Cambio ignorado (\(self.pendingCount)/\(self.requiredConfirmations), conf=\(String(format: "%.3f", confirmed.confianza))): \(confirmed.artista) - \(confirmed.titulo) — manteniendo: \(candidate.artista) - \(candidate.titulo)")
                    }
                }
            }

        } else {
            // ── No hay candidato activo ───────────────────────────────────────
            // Requerir confirmación también para la primera detección.
            // Falsos positivos cambian de canción en cada query; matches reales son estables.
            accumulatePending(track) { [weak self] confirmed in
                guard let self = self else { return }
                if self.pendingCount >= self.requiredConfirmations {
                    print("[Scanner] Primera detección confirmada (\(self.pendingCount)x): \(confirmed.artista) - \(confirmed.titulo)")
                    self.startNewCandidate(from: confirmed)
                    self.resetPending()
                } else {
                    print("[Scanner] Primera detección pendiente (\(self.pendingCount)/\(self.requiredConfirmations)): \(confirmed.artista) - \(confirmed.titulo)")
                }
            }
        }
    }

    /// Acumula confirmaciones para `track`. Si la canción es la misma que la pendiente,
    /// incrementa el contador; si es diferente, reinicia. Ejecuta el bloque siempre.
    private func accumulatePending(_ track: TrackInfo, then block: (TrackInfo) -> Void) {
        let isSamePending: Bool = {
            guard let p = pendingTrack else { return false }
            return p.artista.lowercased() == track.artista.lowercased()
                && p.titulo.lowercased()  == track.titulo.lowercased()
        }()

        if isSamePending {
            pendingCount += 1
        } else {
            pendingTrack  = track
            pendingCount  = 1
        }
        block(track)
    }

    // MARK: - Candidato
    private func startNewCandidate(from track: TrackInfo) {
        let now = Date()

        // Pre-acreditar el tiempo escuchado ANTES de la identificación.
        let audioStart  = ACRScanner.shared.audioDetectedAt
        let preCredit: Double
        if audioStart > .distantPast {
            let elapsed = now.timeIntervalSince(audioStart)
            let cap     = track.duracionSeg > 0 ? track.duracionSeg : 300
            preCredit   = min(elapsed, cap)
        } else {
            preCredit = 0
        }

        currentCandidate = SongCandidate(
            fuente:             track.fuente,
            artista:            track.artista,
            titulo:             track.titulo,
            duracionSeg:        track.duracionSeg,
            isrc:               track.isrc,
            isrcFuente:         track.isrcFuente,
            inCatalog:          track.inCatalog,
            isPromovida:        track.isPromovida,
            confianza:          track.confianza,
            firstSeen:          audioStart > .distantPast ? audioStart : now,
            lastSeen:           now,
            segundosAcumulados: preCredit
        )
        startAccumulation()
        print("[Scanner] Nueva canción: \(track.artista) - \(track.titulo) (\(track.duracionSeg)s) — pre-crédito: \(Int(preCredit))s")
    }

    // MARK: - Acumulación de tiempo
    private func startAccumulation() {
        stopAccumulation()
        accumulationTimer = Timer.scheduledTimer(
            withTimeInterval: accumulationInterval,
            repeats: true
        ) { [weak self] _ in
            self?.accumulateTick()
        }
        RunLoop.main.add(accumulationTimer!, forMode: .common)
    }

    private func stopAccumulation() {
        accumulationTimer?.invalidate()
        accumulationTimer = nil
    }

    private func accumulateTick() {
        guard var candidate = currentCandidate else { stopAccumulation(); return }

        let rms = AudioCaptureManager.shared.currentRMS
        guard rms > audioThreshold else { return }

        candidate.segundosAcumulados += accumulationInterval
        candidate.lastSeen = Date()
        currentCandidate = candidate

        let cfg = config.config
        let duracionValida = candidate.duracionSeg > 0
        let cumpleMinimo   = candidate.segundosAcumulados >= cfg.minDetectionTime

        let cumpleUmbral: Bool
        if duracionValida {
            cumpleUmbral = candidate.porcentaje >= cfg.umbralPorcentaje
        } else {
            // Sin duración conocida: umbral por segundos (minDetectionTime × 2)
            cumpleUmbral = candidate.segundosAcumulados >= cfg.minDetectionTime * 2
        }

        // Al llegar al umbral (80%) → guardar el play PERO seguir monitoreando.
        // El candidato permanece activo hasta que llegue silencio o cambio confirmado,
        // para que la UI muestre el progreso real hasta el 100% y esté lista
        // para detectar la siguiente canción en cuanto termine esta.
        if cumpleMinimo && cumpleUmbral && !candidate.playGuardado {
            var saved = candidate
            saved.playGuardado = true
            currentCandidate = saved
            let pct = duracionValida
                ? min((saved.segundosAcumulados / saved.duracionSeg) * 100, 100)
                : 100.0
            savePlay(saved)
            print("[Scanner] ✅ Play registrado al \(String(format: "%.0f", pct))% — continuando hasta el final…")
            return
        }

        // Sin duración conocida: guardar y resetear a los 3 minutos
        if candidate.segundosAcumulados >= 180 && !duracionValida && !candidate.playGuardado {
            savePlay(candidate)
            currentCandidate = nil
            stopAccumulation()
        }
    }

    // MARK: - Finalizar
    private func finalizeIfEligible(_ candidate: SongCandidate) {
        guard candidate.segundosAcumulados >= 10 else {
            print("[Scanner] Ignorado (< 10s): \(candidate.contenido)")
            return
        }
        guard !candidate.playGuardado else {
            print("[Scanner] Finalizado: \(candidate.contenido) — \(String(format: "%.0f", candidate.porcentaje))% (ya registrado)")
            return
        }
        savePlay(candidate)
    }

    // MARK: - Guardar play
    private func savePlay(_ candidate: SongCandidate) {
        let cfg    = config.config
        let isoFmt = ISO8601DateFormatter()
        let now    = Date()

        let pct: Double
        if candidate.duracionSeg > 0 {
            pct = min((candidate.segundosAcumulados / candidate.duracionSeg) * 100, 100)
        } else {
            pct = 100
        }

        var record = PlayRecord()
        record.idempotencyKey     = candidate.idempotencyKey(venueId: cfg.venueId)
        record.timestamp          = isoFmt.string(from: now)
        record.venueId            = cfg.venueId
        record.fuente             = candidate.fuente
        record.contenido          = candidate.contenido
        record.artista            = candidate.artista
        record.titulo             = candidate.titulo
        record.duracion           = candidate.duracionFormatted
        record.isrc               = candidate.isrc
        record.isrcFuente         = candidate.isrcFuente
        record.inCatalog          = candidate.inCatalog
        record.isPromovida        = candidate.isPromovida
        record.porcentaje         = pct
        record.segundosEscuchados = candidate.segundosAcumulados
        record.duracionSeg        = candidate.duracionSeg
        record.confianza          = candidate.confianza
        record.createdAt          = now.timeIntervalSince1970

        if db.savePlay(record) {
            let catalogTag = candidate.inCatalog ? "✅" : "⚠️ "
            print("[Scanner] \(catalogTag) Play: \(candidate.contenido) — \(String(format: "%.0f", pct))% (\(String(format: "%.0f", candidate.segundosAcumulados))s)")
        }
    }
}
