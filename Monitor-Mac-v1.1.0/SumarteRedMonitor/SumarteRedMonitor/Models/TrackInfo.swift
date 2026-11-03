import Foundation

/// Información de pista detectada por cualquier scanner.
struct TrackInfo {
    var fuente:         String
    var artista:        String
    var titulo:         String
    var duracionSeg:    Double
    var isrc:           String
    var isPlaying:      Bool   = true    // false = pausado (seguimos la pista pero no acumulamos)
    var playerPosition: Double? = nil    // posición real en segundos si el scanner la provee

    var contenido: String { "\(artista) - \(titulo)" }

    var duracionFormatted: String {
        guard duracionSeg > 0 else { return "0:00" }
        let m = Int(duracionSeg) / 60
        let s = Int(duracionSeg) % 60
        return String(format: "%d:%02d", m, s)
    }
}
