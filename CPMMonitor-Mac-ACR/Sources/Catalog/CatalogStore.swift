import Foundation
import SQLite3

/// Gestiona el catálogo local de fingerprints en catalog.db (Application Support).
/// Esquema minimalista: solo lo necesario para matching local y sync incremental.
final class CatalogStore {
    static let shared = CatalogStore()

    private var db: OpaquePointer?
    let dbURL: URL

    private init() {
        let support = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first!
        let dir = support.appendingPathComponent("SumarteRed", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        dbURL = dir.appendingPathComponent("catalog.db")
        open()
        createSchema()
    }

    // MARK: - Schema
    private func open() {
        if sqlite3_open(dbURL.path, &db) != SQLITE_OK {
            print("[CatalogStore] Error abriendo DB: \(String(cString: sqlite3_errmsg(db)))")
        }
        // Migración: agregar is_promovida si no existe (DB de versiones anteriores)
        sqlite3_exec(db,
            "ALTER TABLE tracks ADD COLUMN is_promovida INTEGER NOT NULL DEFAULT 0",
            nil, nil, nil)
    }

    private func createSchema() {
        let sql = """
        CREATE TABLE IF NOT EXISTS tracks (
            id           INTEGER PRIMARY KEY,
            artista      TEXT    NOT NULL DEFAULT '',
            titulo       TEXT    NOT NULL DEFAULT '',
            isrc         TEXT    NOT NULL DEFAULT '',
            duration_seg REAL    NOT NULL DEFAULT 0,
            fp_raw       BLOB    NOT NULL,
            active       INTEGER NOT NULL DEFAULT 1,
            updated_at   INTEGER NOT NULL DEFAULT 0,
            is_promovida INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_updated ON tracks(updated_at);

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO meta(key, value) VALUES ('version', '0');
        INSERT OR IGNORE INTO meta(key, value) VALUES ('last_sync', '0');
        """
        sqlite3_exec(db, sql, nil, nil, nil)
    }

    // MARK: - Version
    var localVersion: Int {
        get { Int(metaValue(for: "version") ?? "0") ?? 0 }
        set { setMeta("version", value: "\(newValue)") }
    }

    var lastSync: Int {
        get { Int(metaValue(for: "last_sync") ?? "0") ?? 0 }
        set { setMeta("last_sync", value: "\(newValue)") }
    }

    var trackCount: Int {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM tracks", -1, &stmt, nil)
        return sqlite3_step(stmt) == SQLITE_ROW ? Int(sqlite3_column_int(stmt, 0)) : 0
    }

    // MARK: - Upsert batch (con transacción para rendimiento)
    /// Inserta o actualiza múltiples tracks en una sola transacción.
    /// Sin transacción: 4500 writes = ~45 segundos. Con transacción: <1 segundo.
    func upsertBatch(_ tracks: [(id: Int, artista: String, titulo: String, isrc: String,
                                 durationSeg: Double, fpRaw: Data, active: Bool,
                                 updatedAt: Int, isPromovida: Bool)]) {
        let sql = """
        INSERT INTO tracks(id, artista, titulo, isrc, duration_seg, fp_raw, active, updated_at, is_promovida)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            artista=excluded.artista, titulo=excluded.titulo, isrc=excluded.isrc,
            duration_seg=excluded.duration_seg, fp_raw=excluded.fp_raw,
            active=excluded.active, updated_at=excluded.updated_at,
            is_promovida=excluded.is_promovida
        """
        sqlite3_exec(db, "BEGIN TRANSACTION", nil, nil, nil)
        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, sql, -1, &stmt, nil)

        for t in tracks {
            sqlite3_reset(stmt)
            sqlite3_bind_int64(stmt, 1, Int64(t.id))
            sqlite3_bind_text(stmt, 2, t.artista,   -1, SQLITE_TRANSIENT)
            sqlite3_bind_text(stmt, 3, t.titulo,    -1, SQLITE_TRANSIENT)
            sqlite3_bind_text(stmt, 4, t.isrc,      -1, SQLITE_TRANSIENT)
            sqlite3_bind_double(stmt, 5, t.durationSeg)
            t.fpRaw.withUnsafeBytes { ptr in
                _ = sqlite3_bind_blob(stmt, 6, ptr.baseAddress, Int32(t.fpRaw.count), SQLITE_TRANSIENT)
            }
            sqlite3_bind_int(stmt, 7, t.active ? 1 : 0)
            sqlite3_bind_int64(stmt, 8, Int64(t.updatedAt))
            sqlite3_bind_int(stmt, 9, t.isPromovida ? 1 : 0)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
        sqlite3_exec(db, "COMMIT", nil, nil, nil)
    }

    /// Upsert individual (para compatibilidad — usa batch de 1 elemento)
    func upsert(id: Int, artista: String, titulo: String, isrc: String,
                durationSeg: Double, fpRaw: Data, active: Bool, updatedAt: Int,
                isPromovida: Bool = false) {
        upsertBatch([(id, artista, titulo, isrc, durationSeg, fpRaw, active, updatedAt, isPromovida)])
    }

    // MARK: - Load all (para LocalMatcher)
    struct CatalogRow {
        let id: Int
        let artista: String
        let titulo: String
        let isrc: String
        let durationSeg: Double
        let fp: [Int32]      // decodificado de fp_raw BLOB
        let active: Bool
        let isPromovida: Bool
    }

    func loadAll() -> [CatalogRow] {
        let sql = "SELECT id, artista, titulo, isrc, duration_seg, fp_raw, active, is_promovida FROM tracks"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        sqlite3_prepare_v2(db, sql, -1, &stmt, nil)

        var rows: [CatalogRow] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let id           = Int(sqlite3_column_int64(stmt, 0))
            let artista      = String(cString: sqlite3_column_text(stmt, 1))
            let titulo       = String(cString: sqlite3_column_text(stmt, 2))
            let isrc         = String(cString: sqlite3_column_text(stmt, 3))
            let duration     = sqlite3_column_double(stmt, 4)
            let active       = sqlite3_column_int(stmt, 6) != 0
            let isPromovida  = sqlite3_column_int(stmt, 7) != 0

            guard let blobPtr = sqlite3_column_blob(stmt, 5) else { continue }
            let blobBytes = Int(sqlite3_column_bytes(stmt, 5))
            let count = blobBytes / 4
            guard count >= 10 else { continue }

            var fp = [Int32](repeating: 0, count: count)
            fp.withUnsafeMutableBytes { dst in
                _ = memcpy(dst.baseAddress, blobPtr, blobBytes)
            }
            rows.append(CatalogRow(
                id: id, artista: artista, titulo: titulo, isrc: isrc,
                durationSeg: duration, fp: fp, active: active, isPromovida: isPromovida
            ))
        }
        return rows
    }

    // MARK: - PromovidaRow (lightweight, no fp_raw BLOB)
    struct PromovidaRow: Identifiable {
        let id: Int
        let artista: String
        let titulo: String
        let isrc: String
        let durationSeg: Double
        var durationFormatted: String {
            guard durationSeg > 0 else { return "—" }
            return String(format: "%d:%02d", Int(durationSeg)/60, Int(durationSeg)%60)
        }
    }

    func fetchPromovidas() -> [PromovidaRow] {
        let sql = "SELECT id, artista, titulo, isrc, duration_seg FROM tracks WHERE active=1 ORDER BY artista, titulo"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        sqlite3_prepare_v2(db, sql, -1, &stmt, nil)

        var rows: [PromovidaRow] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let id          = Int(sqlite3_column_int64(stmt, 0))
            let artista     = String(cString: sqlite3_column_text(stmt, 1))
            let titulo      = String(cString: sqlite3_column_text(stmt, 2))
            let isrc        = String(cString: sqlite3_column_text(stmt, 3))
            let durationSeg = sqlite3_column_double(stmt, 4)
            rows.append(PromovidaRow(id: id, artista: artista, titulo: titulo,
                                     isrc: isrc, durationSeg: durationSeg))
        }
        return rows
    }

    // MARK: - Helpers
    private func metaValue(for key: String) -> String? {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        sqlite3_prepare_v2(db, "SELECT value FROM meta WHERE key=?", -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, key, -1, SQLITE_TRANSIENT)
        guard sqlite3_step(stmt) == SQLITE_ROW,
              let ptr = sqlite3_column_text(stmt, 0) else { return nil }
        return String(cString: ptr)
    }

    private func setMeta(_ key: String, value: String) {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        sqlite3_prepare_v2(db,
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, key,   -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 2, value, -1, SQLITE_TRANSIENT)
        sqlite3_step(stmt)
    }

    deinit { sqlite3_close(db) }
}

// Necesario para pasar punteros C a SQLite sin warnings
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
