import Foundation
import CryptoKit

// MARK: - PlayRecord
struct PlayRecord: Identifiable, Codable {
    var id: Int64 = 0
    var idempotencyKey: String = ""
    var timestamp: String = ""
    var venueId: String = ""
    var fuente: String = ""         // "acr"
    var contenido: String = ""      // "Artista - Título"
    var artista: String = ""
    var titulo: String = ""
    var duracion: String = ""       // "3:42"
    var isrc: String = ""
    var isrcFuente: String = ""     // "sumartred" | "acoustid" | ""
    var inCatalog: Bool = false     // true si está en el catálogo SumarteRed
    var isPromovida: Bool = false   // true si es una canción actualmente promovida
    var porcentaje: Double = 0      // 0-100
    var segundosEscuchados: Double = 0
    var duracionSeg: Double = 0
    var confianza: Double = 0       // score del reconocimiento (0-1)
    var enviado: Bool = false
    var intentos: Int = 0
    var createdAt: Double = 0

    var ganodinero: Bool { porcentaje >= 80 && isPromovida }

    var duracionFormatted: String {
        guard duracionSeg > 0 else { return duracion }
        let m = Int(duracionSeg) / 60
        let s = Int(duracionSeg) % 60
        return String(format: "%d:%02d", m, s)
    }

    var horaFormatted: String {
        let date = Date(timeIntervalSince1970: createdAt)
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }

    var fechaCorta: String {
        let date = Date(timeIntervalSince1970: createdAt)
        let f = DateFormatter()
        f.dateFormat = "dd-MM"
        return f.string(from: date)
    }

    var porcentajeFormatted: String {
        return String(format: "%.0f%%", porcentaje)
    }
}

// MARK: - SongCandidate (tracking en memoria)
struct SongCandidate {
    var fuente: String
    var artista: String
    var titulo: String
    var duracionSeg: Double
    var isrc: String
    var isrcFuente: String
    var inCatalog: Bool
    var isPromovida: Bool
    var confianza: Double
    var firstSeen: Date
    var lastSeen: Date
    var segundosAcumulados: Double
    /// true cuando el play ya fue guardado al llegar al umbral (80%).
    /// Evita guardar doble si finalizeIfEligible se llama al terminar la canción.
    var playGuardado: Bool = false

    var contenido: String { "\(artista) - \(titulo)" }

    var porcentaje: Double {
        guard duracionSeg > 0 else { return 0 }
        return min((segundosAcumulados / duracionSeg) * 100, 100)
    }

    var duracionFormatted: String {
        guard duracionSeg > 0 else { return "0:00" }
        let m = Int(duracionSeg) / 60
        let s = Int(duracionSeg) % 60
        return String(format: "%d:%02d", m, s)
    }

    /// Genera una idempotency key determinista usando SHA-256.
    /// Garantiza que la misma canción en el mismo venue en la misma hora no se duplique,
    /// incluso si la app se reinicia. (Reemplaza hashValue que no es determinista.)
    func idempotencyKey(venueId: String) -> String {
        let ts = Int(Date().timeIntervalSince1970 / 3600)  // ventana de 1 hora
        let raw = "\(venueId)|\(artista.lowercased())|\(titulo.lowercased())|\(ts)"
        let digest = SHA256.hash(data: Data(raw.utf8))
        return digest.compactMap { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - APIPlay (payload para POST /v1/plays)
struct APIPlay: Codable {
    let idempotencyKey:    String
    let timestamp:         String
    let venueId:           String
    let fuente:            String
    let contenido:         String
    let artista:           String
    let titulo:            String
    let duracion:          String
    let isrc:              String
    let isrcFuente:        String
    let inCatalog:         Bool
    let porcentaje:        Double
    let segundosEscuchados: Double
    let duracionSeg:       Double
    let confianza:         Double

    enum CodingKeys: String, CodingKey {
        case idempotencyKey    = "idempotency_key"
        case timestamp
        case venueId           = "venue_id"
        case fuente, contenido, artista, titulo, duracion, isrc
        case isrcFuente        = "isrc_fuente"
        case inCatalog         = "in_catalog"
        case porcentaje
        case segundosEscuchados = "segundos_escuchados"
        case duracionSeg       = "duracion_seg"
        case confianza
    }
}
