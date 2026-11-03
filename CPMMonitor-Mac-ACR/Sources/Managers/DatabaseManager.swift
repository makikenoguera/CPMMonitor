import Foundation
import SQLite3

// SQLITE_TRANSIENT es una macro C que no se importa directamente en Swift
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

class DatabaseManager {
    static let shared = DatabaseManager()
    private var db: OpaquePointer?

    private var dbPath: String {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = support.appendingPathComponent("SumarteRed")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("sumartered_plays_v3.db").path
    }

    private init() {}

    // MARK: - Init DB
    func initializeDatabase() {
        guard sqlite3_open(dbPath, &db) == SQLITE_OK else {
            print("[DB] No se pudo abrir la base de datos")
            return
        }
        let sql = """
        CREATE TABLE IF NOT EXISTS plays (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key     TEXT UNIQUE NOT NULL,
            timestamp           TEXT NOT NULL,
            venue_id            TEXT NOT NULL DEFAULT '',
            fuente              TEXT NOT NULL,
            contenido           TEXT NOT NULL,
            artista             TEXT NOT NULL DEFAULT '',
            titulo              TEXT NOT NULL DEFAULT '',
            duracion            TEXT NOT NULL,
            isrc                TEXT NOT NULL DEFAULT '',
            isrc_fuente         TEXT NOT NULL DEFAULT '',
            in_catalog          INTEGER NOT NULL DEFAULT 0,
            porcentaje          REAL NOT NULL DEFAULT 0,
            segundos_escuchados REAL NOT NULL DEFAULT 0,
            duracion_seg        REAL NOT NULL DEFAULT 0,
            confianza           REAL NOT NULL DEFAULT 0,
            enviado             INTEGER NOT NULL DEFAULT 0,
            intentos            INTEGER NOT NULL DEFAULT 0,
            created_at          REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enviado    ON plays(enviado);
        CREATE INDEX IF NOT EXISTS idx_created_at ON plays(created_at);
        CREATE INDEX IF NOT EXISTS idx_in_catalog ON plays(in_catalog);
        """
        sqlite3_exec(db, sql, nil, nil, nil)
        // Migración: agregar is_promovida si no existe (DB de versiones anteriores)
        sqlite3_exec(db,
            "ALTER TABLE plays ADD COLUMN is_promovida INTEGER NOT NULL DEFAULT 0",
            nil, nil, nil)
        print("[DB] Base de datos lista: \(dbPath)")
    }

    // MARK: - Guardar play
    func savePlay(_ record: PlayRecord) -> Bool {
        let sql = """
        INSERT OR IGNORE INTO plays
        (idempotency_key, timestamp, venue_id, fuente, contenido, artista, titulo,
         duracion, isrc, isrc_fuente, in_catalog, is_promovida,
         porcentaje, segundos_escuchados, duracion_seg, confianza,
         enviado, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)
        """
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return false }
        sqlite3_bind_text  (stmt,  1, record.idempotencyKey,         -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  2, record.timestamp,              -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  3, record.venueId,                -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  4, record.fuente,                 -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  5, record.contenido,              -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  6, record.artista,                -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  7, record.titulo,                 -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  8, record.duracion,               -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt,  9, record.isrc,                   -1, SQLITE_TRANSIENT)
        sqlite3_bind_text  (stmt, 10, record.isrcFuente,             -1, SQLITE_TRANSIENT)
        sqlite3_bind_int   (stmt, 11, record.inCatalog   ? 1 : 0)
        sqlite3_bind_int   (stmt, 12, record.isPromovida ? 1 : 0)
        sqlite3_bind_double(stmt, 13, record.porcentaje)
        sqlite3_bind_double(stmt, 14, record.segundosEscuchados)
        sqlite3_bind_double(stmt, 15, record.duracionSeg)
        sqlite3_bind_double(stmt, 16, record.confianza)
        sqlite3_bind_double(stmt, 17, record.createdAt)
        let result = sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        return result == SQLITE_DONE
    }

    // MARK: - Stats
    struct PlayStats {
        var totalPlays: Int = 0    // today
        var catalogPlays: Int = 0  // today, in_catalog=1 AND porcentaje>=80
        var periodPlays: Int = 0
        var periodCatalog: Int = 0
    }

    func fetchStats(from startDate: Date? = nil, to endDate: Date? = nil) -> PlayStats {
        // created_at se guarda como REAL (Unix timestamp en segundos).
        // Usar sqlite3_bind_double para evitar la comparación TEXT vs REAL de SQLite
        // (SQLite ordena REAL < TEXT, lo que hace que la condición >= siempre sea false
        // cuando se vincula una cadena ISO contra una columna numérica).

        let calendar   = Calendar.current
        let todayStart = calendar.startOfDay(for: Date())
        let todayTs    = todayStart.timeIntervalSince1970

        var stats = PlayStats()

        // Query 1: Hoy
        let sqlToday = "SELECT COUNT(*), SUM(CASE WHEN in_catalog=1 AND porcentaje>=80 THEN 1 ELSE 0 END) FROM plays WHERE created_at >= ?"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sqlToday, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_double(stmt, 1, todayTs)
            if sqlite3_step(stmt) == SQLITE_ROW {
                stats.totalPlays   = Int(sqlite3_column_int(stmt, 0))
                stats.catalogPlays = Int(sqlite3_column_int(stmt, 1))
            }
            sqlite3_finalize(stmt)
        }

        // Query 2: Período (predeterminado: hoy 00:00 → ahora)
        let start   = startDate ?? todayStart
        let end     = endDate   ?? Date()
        let startTs = start.timeIntervalSince1970
        let endTs   = end.timeIntervalSince1970

        let sqlPeriod = "SELECT COUNT(*), SUM(CASE WHEN in_catalog=1 AND porcentaje>=80 THEN 1 ELSE 0 END) FROM plays WHERE created_at >= ? AND created_at <= ?"
        var stmt2: OpaquePointer?
        if sqlite3_prepare_v2(db, sqlPeriod, -1, &stmt2, nil) == SQLITE_OK {
            sqlite3_bind_double(stmt2, 1, startTs)
            sqlite3_bind_double(stmt2, 2, endTs)
            if sqlite3_step(stmt2) == SQLITE_ROW {
                stats.periodPlays   = Int(sqlite3_column_int(stmt2, 0))
                stats.periodCatalog = Int(sqlite3_column_int(stmt2, 1))
            }
            sqlite3_finalize(stmt2)
        }

        return stats
    }

    // MARK: - Pendientes (para enviar al servidor)
    func fetchPending(limit: Int = 50) -> [PlayRecord] {
        let sql = """
        SELECT id, idempotency_key, timestamp, venue_id, fuente, contenido, artista, titulo,
               duracion, isrc, isrc_fuente, in_catalog, is_promovida,
               porcentaje, segundos_escuchados, duracion_seg, confianza,
               intentos, created_at
        FROM plays WHERE enviado=0 AND intentos<20
        ORDER BY created_at ASC LIMIT ?
        """
        return query(sql: sql, limit: limit)
    }

    // MARK: - Plays en rango de fechas (para Ganancias)
    func fetchPlaysInRange(from startDate: Date, to endDate: Date) -> [PlayRecord] {
        let sql = """
        SELECT id, idempotency_key, timestamp, venue_id, fuente, contenido, artista, titulo,
               duracion, isrc, isrc_fuente, in_catalog, is_promovida,
               porcentaje, segundos_escuchados, duracion_seg, confianza,
               intentos, created_at, enviado
        FROM plays
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at DESC
        """
        var stmt: OpaquePointer?
        var records: [PlayRecord] = []
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        sqlite3_bind_double(stmt, 1, startDate.timeIntervalSince1970)
        sqlite3_bind_double(stmt, 2, endDate.timeIntervalSince1970)
        while sqlite3_step(stmt) == SQLITE_ROW {
            var r = PlayRecord()
            r.id                 = sqlite3_column_int64 (stmt,  0)
            r.idempotencyKey     = col_text(stmt,  1)
            r.timestamp          = col_text(stmt,  2)
            r.venueId            = col_text(stmt,  3)
            r.fuente             = col_text(stmt,  4)
            r.contenido          = col_text(stmt,  5)
            r.artista            = col_text(stmt,  6)
            r.titulo             = col_text(stmt,  7)
            r.duracion           = col_text(stmt,  8)
            r.isrc               = col_text(stmt,  9)
            r.isrcFuente         = col_text(stmt, 10)
            r.inCatalog          = sqlite3_column_int(stmt, 11) == 1
            r.isPromovida        = sqlite3_column_int(stmt, 12) == 1
            r.porcentaje         = sqlite3_column_double(stmt, 13)
            r.segundosEscuchados = sqlite3_column_double(stmt, 14)
            r.duracionSeg        = sqlite3_column_double(stmt, 15)
            r.confianza          = sqlite3_column_double(stmt, 16)
            r.intentos           = Int(sqlite3_column_int(stmt, 17))
            r.createdAt          = sqlite3_column_double(stmt, 18)
            r.enviado            = sqlite3_column_int(stmt, 19) == 1
            records.append(r)
        }
        sqlite3_finalize(stmt)
        return records
    }

    // MARK: - Historial reciente
    func fetchHistory(limit: Int = 50) -> [PlayRecord] {
        let sql = """
        SELECT id, idempotency_key, timestamp, venue_id, fuente, contenido, artista, titulo,
               duracion, isrc, isrc_fuente, in_catalog, is_promovida,
               porcentaje, segundos_escuchados, duracion_seg, confianza,
               intentos, created_at, enviado
        FROM plays ORDER BY created_at DESC LIMIT ?
        """
        return query(sql: sql, limit: limit, includeEnviado: true)
    }

    // MARK: - Query helper
    private func query(sql: String, limit: Int, includeEnviado: Bool = false) -> [PlayRecord] {
        var stmt: OpaquePointer?
        var records: [PlayRecord] = []
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        sqlite3_bind_int(stmt, 1, Int32(limit))

        while sqlite3_step(stmt) == SQLITE_ROW {
            var r = PlayRecord()
            r.id                 = sqlite3_column_int64 (stmt,  0)
            r.idempotencyKey     = col_text(stmt,  1)
            r.timestamp          = col_text(stmt,  2)
            r.venueId            = col_text(stmt,  3)
            r.fuente             = col_text(stmt,  4)
            r.contenido          = col_text(stmt,  5)
            r.artista            = col_text(stmt,  6)
            r.titulo             = col_text(stmt,  7)
            r.duracion           = col_text(stmt,  8)
            r.isrc               = col_text(stmt,  9)
            r.isrcFuente         = col_text(stmt, 10)
            r.inCatalog          = sqlite3_column_int(stmt, 11) == 1
            r.isPromovida        = sqlite3_column_int(stmt, 12) == 1
            r.porcentaje         = sqlite3_column_double(stmt, 13)
            r.segundosEscuchados = sqlite3_column_double(stmt, 14)
            r.duracionSeg        = sqlite3_column_double(stmt, 15)
            r.confianza          = sqlite3_column_double(stmt, 16)
            r.intentos           = Int(sqlite3_column_int(stmt, 17))
            r.createdAt          = sqlite3_column_double(stmt, 18)
            if includeEnviado {
                r.enviado = sqlite3_column_int(stmt, 19) == 1
            }
            records.append(r)
        }
        sqlite3_finalize(stmt)
        return records
    }

    private func col_text(_ stmt: OpaquePointer?, _ idx: Int32) -> String {
        guard let ptr = sqlite3_column_text(stmt, idx) else { return "" }
        return String(cString: ptr)
    }

    // MARK: - Actualizaciones
    func markSent(_ id: Int64) {
        let sql = "UPDATE plays SET enviado=1 WHERE id=?"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_int64(stmt, 1, id)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
    }

    func incrementAttempts(_ id: Int64) {
        let sql = "UPDATE plays SET intentos=intentos+1 WHERE id=?"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_int64(stmt, 1, id)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
    }

    func countPending() -> Int {
        let sql = "SELECT COUNT(*) FROM plays WHERE enviado=0"
        var stmt: OpaquePointer?
        var count = 0
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            if sqlite3_step(stmt) == SQLITE_ROW {
                count = Int(sqlite3_column_int(stmt, 0))
            }
            sqlite3_finalize(stmt)
        }
        return count
    }
}
