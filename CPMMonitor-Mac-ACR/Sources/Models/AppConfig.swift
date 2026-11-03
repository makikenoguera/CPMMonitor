import Foundation

/// Configuración persistente del monitor.
/// v3.0: autenticación por API key por venue (reemplaza sessionToken + login).
struct AppConfig: Codable {
    var venueId:          String = ""   // ID único del venue (ej: "VENUE-001")
    var apiKey:           String = ""   // API key del venue (UUID o string aleatorio)
    var nombreLocal:      String = ""   // Nombre legible del venue
    var serverURL:        String = "https://monitor.sumartered.com"
    var launchAtLogin:    Bool   = true
    var minDetectionTime: Double = 15.0  // segundos mínimos escuchados para registrar
    var umbralPorcentaje: Double = 80.0  // % de la canción escuchado para contar
    var scoreThreshold:   Double = 0.80  // confianza mínima del reconocimiento (0-1)
    var tarifaPlay:       Double = 500.0 // COP por play efectivo (≥80%)

    // MARK: - Codable
    // CodingKeys usa solo las propiedades actuales → encode() generado automáticamente.
    enum CodingKeys: String, CodingKey {
        case venueId, apiKey, nombreLocal, serverURL
        case launchAtLogin, minDetectionTime, umbralPorcentaje, scoreThreshold
        case tarifaPlay
    }

    // AllCodingKeys incluye claves legacy para migración en el decoder.
    private enum AllCodingKeys: String, CodingKey {
        case venueId, apiKey, nombreLocal, serverURL
        case launchAtLogin, minDetectionTime, umbralPorcentaje, scoreThreshold
        case tarifaPlay
        // Legacy v2.x (solo decodificación)
        case idLocal, sessionToken, acoustidApiKey, apiBaseURL
    }

    init() {}

    // Decoder tolerante: lee claves nuevas o migra desde legacy.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AllCodingKeys.self)

        venueId          = (try? c.decode(String.self,  forKey: .venueId))          ?? ""
        apiKey           = (try? c.decode(String.self,  forKey: .apiKey))           ?? ""
        nombreLocal      = (try? c.decode(String.self,  forKey: .nombreLocal))      ?? ""
        serverURL        = (try? c.decode(String.self,  forKey: .serverURL))
                        ?? (try? c.decode(String.self,  forKey: .apiBaseURL))
                        ?? "https://monitor.sumartered.com"
        launchAtLogin    = (try? c.decode(Bool.self,    forKey: .launchAtLogin))    ?? true
        minDetectionTime = (try? c.decode(Double.self,  forKey: .minDetectionTime)) ?? 15.0
        umbralPorcentaje = (try? c.decode(Double.self,  forKey: .umbralPorcentaje)) ?? 80.0
        scoreThreshold   = (try? c.decode(Double.self,  forKey: .scoreThreshold))   ?? 0.80
        tarifaPlay       = (try? c.decode(Double.self,  forKey: .tarifaPlay))       ?? 500.0

        // Migración v2.x → v3.0: idLocal → venueId
        if venueId.isEmpty {
            venueId = (try? c.decode(String.self, forKey: .idLocal)) ?? ""
        }
    }
}
