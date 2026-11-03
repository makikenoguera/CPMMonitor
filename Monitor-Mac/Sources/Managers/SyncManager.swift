import Foundation

class SyncManager {
    static let shared = SyncManager()

    private let db        = DatabaseManager.shared
    private let api       = APIClient.shared
    private var timer:      Timer?
    private var isSyncing = false

    private init() {}

    // MARK: - Control
    func start() {
        scheduleTimer()
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in
            self?.syncPending()
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    // MARK: - Timer
    private func scheduleTimer() {
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            self?.syncPending()
        }
        RunLoop.main.add(timer!, forMode: .common)
    }

    // MARK: - Sync
    func syncPending() {
        guard !isSyncing else { return }
        let pending = db.fetchPending(limit: 50)
        guard !pending.isEmpty else { return }

        isSyncing = true
        print("[Sync] Enviando \(pending.count) plays pendientes…")

        let apiPlays = pending.map { r in
            APIPlay(
                idempotencyKey:     r.idempotencyKey,
                timestamp:          r.timestamp,
                venueId:            r.venueId,
                fuente:             r.fuente,
                contenido:          r.contenido,
                artista:            r.artista,
                titulo:             r.titulo,
                duracion:           r.duracion,
                isrc:               r.isrc,
                isrcFuente:         r.isrcFuente,
                inCatalog:          r.inCatalog,
                porcentaje:         r.porcentaje,
                segundosEscuchados: r.segundosEscuchados,
                duracionSeg:        r.duracionSeg,
                confianza:          r.confianza
            )
        }

        api.sendPlays(apiPlays) { [weak self] result in
            guard let self = self else { return }
            self.isSyncing = false

            switch result {
            case .success(let resp):
                // Marcar todos como enviados (aceptados o ya existentes en servidor)
                let aceptados = Set(resp.accepted ?? [])
                var count = 0
                for record in pending {
                    // Si el servidor acepta idempotency keys → marcar solo esos
                    // Si el servidor no devuelve accepted → marcar todos
                    if aceptados.isEmpty || aceptados.contains(record.idempotencyKey) {
                        self.db.markSent(record.id)
                        count += 1
                    } else {
                        self.db.incrementAttempts(record.id)
                    }
                }
                print("[Sync] OK — enviados: \(count) / \(pending.count)")

            case .failure(let err):
                pending.forEach { self.db.incrementAttempts($0.id) }
                print("[Sync] Error: \(err.localizedDescription)")
            }
        }
    }
}
