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
        // Sync inmediato al iniciar
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
                idempotencyKey:   r.idempotencyKey,
                timestamp:        r.timestamp,
                idLocal:          r.idLocal,
                fuente:           r.fuente,
                contenido:        r.contenido,
                duracion:         r.duracion,
                isrc:             r.isrc,
                porcentaje:       r.porcentaje,
                segundosEscuchados: r.segundosEscuchados,
                duracionSeg:      r.duracionSeg
            )
        }

        api.sendPlays(apiPlays) { [weak self] result in
            guard let self = self else { return }
            self.isSyncing = false

            switch result {
            case .success(let resp):
                let aceptados = Set(resp.accepted ?? [])
                var enviados = 0
                for record in pending {
                    if aceptados.contains(record.idempotencyKey) {
                        self.db.markSent(record.id)
                        enviados += 1
                    } else {
                        // El servidor lo rechazó (duplicado o error) — marcarlo como enviado
                        // para no reintentarlo infinitamente si ya estaba en el servidor
                        self.db.markSent(record.id)
                        enviados += 1
                    }
                }
                print("[Sync] OK — enviados: \(enviados) / \(pending.count)")
            case .failure(let err):
                pending.forEach { self.db.incrementAttempts($0.id) }
                print("[Sync] Error: \(err.localizedDescription)")
            }
        }
    }
}
