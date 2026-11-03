import Foundation

// MARK: - PlayRecord
struct PlayRecord: Identifiable, Codable {
    var id: Int64 = 0
    var idempotencyKey: String = ""
    var timestamp: String = ""
    var idLocal: String = ""
    var fuente: String = ""         // "spotify", "applemusic", "youtube", "vlc"
    var contenido: String = ""      // "Artista - Título"
    var artista: String = ""
    var titulo: String = ""
    var duracion: String = ""       // "3:42"
    var isrc: String = ""
    var porcentaje: Double = 0      // 0-100
    var segundosEscuchados: Double = 0
    var duracionSeg: Double = 0
    var enviado: Bool = false
    var intentos: Int = 0
    var createdAt: Double = 0

    // Computed
    var ganodinero: Bool { porcentaje >= 90 }

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
    var firstSeen: Date
    var lastSeen: Date
    var segundosAcumulados: Double
    var lastPlayerPosition: Double? = nil  // última posición real del reproductor

    var contenido: String { "\(artista) - \(titulo)" }

    var porcentaje: Double {
        guard duracionSeg > 0 else { return 0 }
        return min((segundosAcumulados / duracionSeg) * 100, 100)
    }

    /// Porcentaje de posición actual (para mostrar en UI, diferente de "escuchado")
    var posicionPct: Double {
        guard duracionSeg > 0 else { return porcentaje }
        if let pos = lastPlayerPosition {
            return min((pos / duracionSeg) * 100, 100)
        }
        return porcentaje
    }

    var duracionFormatted: String {
        guard duracionSeg > 0 else { return "0:00" }
        let m = Int(duracionSeg) / 60
        let s = Int(duracionSeg) % 60
        return String(format: "%d:%02d", m, s)
    }

    func idempotencyKey(idLocal: String) -> String {
        let normalized = "\(fuente)|\(artista.lowercased())|\(titulo.lowercased())"
        let hash = abs(normalized.hashValue)
        let ts   = Int(Date().timeIntervalSince1970 / 3600)
        return "\(idLocal)_\(hash)_\(ts)"
    }

    /// Actualiza el candidato con la nueva posición real del reproductor.
    /// Solo acumula segundos escuchados cuando el movimiento es plausible (sin saltos de seek).
    mutating func update(at date: Date, interval: Double, playerPosition: Double? = nil) {
        lastSeen = date

        if let pos = playerPosition, let lastPos = lastPlayerPosition {
            let delta = pos - lastPos
            // Solo acumular si el avance es positivo y razonable (no un salto de seek)
            if delta > 0 && delta <= interval * 2.5 {
                segundosAcumulados += delta
            }
            // Si delta < 0 → retrocedieron / reiniciaron → no acumular
            // Si delta >> interval → adelantaron → no acumular esa parte saltada
        } else if playerPosition == nil {
            // Fuente sin posición real (VLC sin AppleScript completo) → usar intervalo
            segundosAcumulados += interval
        }
        // Si playerPosition existe pero lastPlayerPosition era nil → primera lectura, solo guardar posición

        lastPlayerPosition = playerPosition
    }
}

// MARK: - APIPlay (payload para el servidor)
struct APIPlay: Codable {
    let idempotencyKey: String
    let timestamp: String
    let idLocal: String
    let fuente: String
    let contenido: String
    let duracion: String
    let isrc: String
    let porcentaje: Double
    let segundosEscuchados: Double
    let duracionSeg: Double

    enum CodingKeys: String, CodingKey {
        case idempotencyKey = "idempotency_key"
        case timestamp, idLocal = "id_local"
        case fuente, contenido, duracion, isrc
        case porcentaje
        case segundosEscuchados = "segundos_escuchados"
        case duracionSeg = "duracion_seg"
    }
}
