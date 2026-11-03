import Foundation

/// Información de pista detectada por el scanner ACR.
struct TrackInfo {
    var fuente:         String
    var artista:        String
    var titulo:         String
    var duracionSeg:    Double
    var isrc:           String
    var isrcFuente:     String   // "sumartered" | "acoustid" | ""
    var inCatalog:      Bool     // true si está en el catálogo SumarteRed
    var isPromovida:    Bool     // true si es una canción actualmente promovida
    var confianza:      Double   // 0.0 - 1.0 (score del reconocimiento)
    var isPlaying:      Bool   = true
    var playerPosition: Double? = nil

    var contenido: String { "\(artista) - \(titulo)" }

    var duracionFormatted: String {
        guard duracionSeg > 0 else { return "0:00" }
        let m = Int(duracionSeg) / 60
        let s = Int(duracionSeg) % 60
        return String(format: "%d:%02d", m, s)
    }
}
