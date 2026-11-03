import Foundation
import Combine

/// Sincroniza el catálogo local con el servidor de forma silenciosa.
///
/// Flujo:
///   1. Al arrancar: si catalog.db está vacío → descarga full
///   2. Al arrancar + cada 6h: GET /v1/catalog/version
///      · Si version servidor > version local → descarga delta
///      · Aplica delta al DB → recarga LocalMatcher
///   3. Nadie en la UI necesita ver este proceso (silent background sync)
final class CatalogManager: ObservableObject {
    static let shared = CatalogManager()

    enum SyncStatus: Equatable {
        case idle
        case checking
        case downloading(Int)   // N tracks recibidos
        case upToDate
        case error(String)
    }

    @Published var syncStatus: SyncStatus = .idle
    @Published var catalogCount: Int = 0

    private var updateTimer: Timer?
    private let store   = CatalogStore.shared
    private let matcher = LocalMatcher.shared

    private init() {}

    // MARK: - Arranque
    func start() {
        // Cargar lo que ya hay en disco (puede ser 0 tracks en primera instalación)
        matcher.reload()
        catalogCount = matcher.trackCount

        Task {
            if store.trackCount == 0 {
                // Primera instalación: descarga completa
                await downloadFull()
            } else {
                // Instalaciones existentes: solo delta
                await checkForUpdates()
            }
        }

        // Verificar actualizaciones cada 6 horas
        updateTimer = Timer.scheduledTimer(withTimeInterval: 6 * 3600, repeats: true) { [weak self] _ in
            Task { await self?.checkForUpdates() }
        }
    }

    // MARK: - Check version
    func checkForUpdates() async {
        await MainActor.run { syncStatus = .checking }

        let cfg = ConfigManager.shared.config
        guard !cfg.apiKey.isEmpty, !cfg.serverURL.isEmpty else { return }

        guard let url = URL(string: "\(cfg.serverURL)/v1/catalog/version") else { return }
        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue(cfg.apiKey, forHTTPHeaderField: "X-API-Key")

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let serverVersion = json["version"] as? Int else {
                await MainActor.run { syncStatus = .upToDate }
                return
            }

            let localVersion = store.localVersion
            print("[CatalogManager] version local=\(localVersion) servidor=\(serverVersion)")

            if serverVersion > localVersion {
                await downloadDelta(since: localVersion)
            } else {
                await MainActor.run { syncStatus = .upToDate }
            }
        } catch {
            print("[CatalogManager] Error verificando versión: \(error.localizedDescription)")
            await MainActor.run { syncStatus = .idle }
        }
    }

    // MARK: - Download full (primera instalación)
    func downloadFull() async {
        print("[CatalogManager] Descargando catálogo completo…")
        await MainActor.run { syncStatus = .downloading(0) }

        let cfg = ConfigManager.shared.config
        guard !cfg.apiKey.isEmpty, !cfg.serverURL.isEmpty,
              let url = URL(string: "\(cfg.serverURL)/v1/catalog/full") else { return }

        var req = URLRequest(url: url, timeoutInterval: 120)
        req.setValue(cfg.apiKey, forHTTPHeaderField: "X-API-Key")

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let count = try await applyResponse(data: data)
            print("[CatalogManager] Catálogo completo descargado: \(count) tracks")
        } catch {
            print("[CatalogManager] Error descargando catálogo: \(error.localizedDescription)")
            await MainActor.run { syncStatus = .error(error.localizedDescription) }
        }
    }

    // MARK: - Download delta (actualizaciones)
    private func downloadDelta(since: Int) async {
        print("[CatalogManager] Descargando delta desde \(since)…")
        await MainActor.run { syncStatus = .downloading(0) }

        let cfg = ConfigManager.shared.config
        guard !cfg.apiKey.isEmpty, !cfg.serverURL.isEmpty,
              let url = URL(string: "\(cfg.serverURL)/v1/catalog/delta?since=\(since)") else { return }

        var req = URLRequest(url: url, timeoutInterval: 60)
        req.setValue(cfg.apiKey, forHTTPHeaderField: "X-API-Key")

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let count = try await applyResponse(data: data)
            if count > 0 {
                print("[CatalogManager] Delta aplicado: \(count) tracks nuevos/actualizados")
            } else {
                print("[CatalogManager] Sin tracks nuevos en el delta")
            }
        } catch {
            print("[CatalogManager] Error descargando delta: \(error.localizedDescription)")
            await MainActor.run { syncStatus = .error(error.localizedDescription) }
        }
    }

    // MARK: - Aplicar respuesta JSON al DB
    /// Parsea el JSON del servidor, guarda tracks en DB, recarga el matcher.
    /// Retorna el número de tracks procesados.
    @discardableResult
    private func applyResponse(data: Data) async throws -> Int {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw SyncError.invalidJSON
        }
        let serverVersion = json["version"] as? Int ?? 0
        let tracks = json["tracks"] as? [[String: Any]] ?? []

        // Parsear todos los tracks primero, luego insertar en una sola transacción
        var batch: [(id: Int, artista: String, titulo: String, isrc: String,
                     durationSeg: Double, fpRaw: Data, active: Bool,
                     updatedAt: Int, isPromovida: Bool)] = []
        for t in tracks {
            guard
                let id          = t["id"]          as? Int,
                let artista     = t["artista"]      as? String,
                let titulo      = t["titulo"]       as? String,
                let durationSeg = t["duration_seg"] as? Double,
                let fpBase64    = t["fp_raw"]       as? String,
                let fpData      = Data(base64Encoded: fpBase64),
                fpData.count >= 40   // mínimo 10 int32 = 40 bytes
            else { continue }

            let isrc        = t["isrc"]         as? String ?? ""
            let active      = t["active"]       as? Bool   ?? true
            let updatedAt   = t["updated_at"]   as? Int    ?? 0
            let isPromovida = t["is_promovida"] as? Bool   ?? false
            batch.append((id, artista, titulo, isrc, durationSeg, fpData, active, updatedAt, isPromovida))
        }

        // Una sola transacción: 4500 inserts en <1 segundo
        store.upsertBatch(batch)
        let saved = batch.count

        if serverVersion > 0 {
            store.localVersion = serverVersion
            store.lastSync     = Int(Date().timeIntervalSince1970)
        }

        // Recargar el índice en memoria
        matcher.reload()
        let count = matcher.trackCount
        await MainActor.run {
            self.catalogCount = count
            self.syncStatus   = .upToDate
        }
        return saved
    }

    enum SyncError: Error {
        case invalidJSON
        case noConfig
    }
}
