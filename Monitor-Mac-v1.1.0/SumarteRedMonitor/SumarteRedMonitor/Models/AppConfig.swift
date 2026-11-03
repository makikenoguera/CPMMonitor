import Foundation

struct AppConfig: Codable {
    var idLocal: String = ""
    var sessionToken: String = ""
    var nombreLocal: String = ""
    var apiBaseURL: String = "https://monitor.cpmtracks.com"
    var launchAtLogin: Bool = true
    var scanInterval: Double = 3.0        // segundos entre scans
    var minDetectionTime: Double = 15.0   // mínimo para registrar un play
    var umbralPorcentaje: Double = 90.0   // % mínimo para contar como ganancia
    var enableYouTubeScanner: Bool = false // YouTube: deshabilitado por defecto (mucho ruido)
}
