import Foundation
import SQLite3

// SQLITE_TRANSIENT es una macro C que no se importa directamente en Swift
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

class DatabaseManager {
    static let shared = DatabaseManager()
    private var db: OpaquePointer?

    private var dbPath: String {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = support.appendingPathComponent("CPMTracks")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("cpm_tracks.db").path
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
            id_local            TEXT NOT NULL,
            fuente              TEXT NOT NULL,
            contenido           TEXT NOT NULL,
            duracion            TEXT NOT NULL,
            isrc                TEXT NOT NULL,
            porcentaje          REAL NOT NULL DEFAULT 0,
            segundos_escuchados REAL NOT NULL DEFAULT 0,
            duracion_seg        REAL NOT NULL DEFAULT 0,
            enviado             INTEGER NOT NULL DEFAULT 0,
            intentos            INTEGER NOT NULL DEFAULT 0,
            created_at          REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enviado ON plays(enviado);
        """
        sqlite3_exec(db, sql, nil, nil, nil)
    }

    // MARK: - Guardar play
    func savePlay(_ record: PlayRecord) -> Bool {
        let sql = """
        INSERT OR IGNORE INTO plays
        (idempotency_key,timestamp,id_local,fuente,contenido,duracion,isrc,
         porcentaje,segundos_escuchados,duracion_seg,enviado,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,0,?)
        """
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return false }
        sqlite3_bind_text(stmt, 1, record.idempotencyKey, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 2, record.timestamp, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 3, record.idLocal, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 4, record.fuente, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 5, record.contenido, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 6, record.duracion, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmt, 7, record.isrc, -1, SQLITE_TRANSIENT)
        sqlite3_bind_double(stmt, 8, record.porcentaje)
        sqlite3_bind_double(stmt, 9, record.segundosEscuchados)
        sqlite3_bind_double(stmt, 10, record.duracionSeg)
        sqlite3_bind_double(stmt, 11, record.createdAt)
        let result = sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        return result == SQLITE_DONE
    }

    // MARK: - Pendientes
    func fetchPending(limit: Int = 50) -> [PlayRecord] {
        let sql = """
        SELECT id,idempotency_key,timestamp,id_local,fuente,contenido,duracion,isrc,
               intentos,porcentaje,segundos_escuchados,duracion_seg,created_at
        FROM plays WHERE enviado=0 AND intentos<20
        ORDER BY created_at ASC LIMIT ?
        """
        var stmt: OpaquePointer?
        var records: [PlayRecord] = []
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        sqlite3_bind_int(stmt, 1, Int32(limit))
        while sqlite3_step(stmt) == SQLITE_ROW {
            var r = PlayRecord()
            r.id               = sqlite3_column_int64(stmt, 0)
            r.idempotencyKey   = String(cString: sqlite3_column_text(stmt, 1))
            r.timestamp        = String(cString: sqlite3_column_text(stmt, 2))
            r.idLocal          = String(cString: sqlite3_column_text(stmt, 3))
            r.fuente           = String(cString: sqlite3_column_text(stmt, 4))
            r.contenido        = String(cString: sqlite3_column_text(stmt, 5))
            r.duracion         = String(cString: sqlite3_column_text(stmt, 6))
            r.isrc             = String(cString: sqlite3_column_text(stmt, 7))
            r.intentos         = Int(sqlite3_column_int(stmt, 8))
            r.porcentaje       = sqlite3_column_double(stmt, 9)
            r.segundosEscuchados = sqlite3_column_double(stmt, 10)
            r.duracionSeg      = sqlite3_column_double(stmt, 11)
            r.createdAt        = sqlite3_column_double(stmt, 12)
            records.append(r)
        }
        sqlite3_finalize(stmt)
        return records
    }

    // MARK: - Historial reciente
    func fetchHistory(limit: Int = 50) -> [PlayRecord] {
        let sql = """
        SELECT id,idempotency_key,timestamp,id_local,fuente,contenido,duracion,isrc,
               intentos,porcentaje,segundos_escuchados,duracion_seg,created_at,enviado
        FROM plays ORDER BY created_at DESC LIMIT ?
        """
        var stmt: OpaquePointer?
        var records: [PlayRecord] = []
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        sqlite3_bind_int(stmt, 1, Int32(limit))
        while sqlite3_step(stmt) == SQLITE_ROW {
            var r = PlayRecord()
            r.id               = sqlite3_column_int64(stmt, 0)
            r.idempotencyKey   = String(cString: sqlite3_column_text(stmt, 1))
            r.timestamp        = String(cString: sqlite3_column_text(stmt, 2))
            r.idLocal          = String(cString: sqlite3_column_text(stmt, 3))
            r.fuente           = String(cString: sqlite3_column_text(stmt, 4))
            r.contenido        = String(cString: sqlite3_column_text(stmt, 5))
            r.duracion         = String(cString: sqlite3_column_text(stmt, 6))
            r.isrc             = String(cString: sqlite3_column_text(stmt, 7))
            r.intentos         = Int(sqlite3_column_int(stmt, 8))
            r.porcentaje       = sqlite3_column_double(stmt, 9)
            r.segundosEscuchados = sqlite3_column_double(stmt, 10)
            r.duracionSeg      = sqlite3_column_double(stmt, 11)
            r.createdAt        = sqlite3_column_double(stmt, 12)
            r.enviado          = sqlite3_column_int(stmt, 13) == 1
            records.append(r)
        }
        sqlite3_finalize(stmt)
        return records
    }

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
