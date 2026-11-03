import Foundation

/// Cliente HTTP para la API gratuita de AcousticID (acoustid.org).
/// Envía fingerprint Chromaprint + duración, recibe metadatos de la canción.
/// API key gratuita en: https://acoustid.org/login
struct AcousticIDClient {

    private static let apiURL = "https://api.acoustid.org/v2/lookup"

    // MARK: - Modelos de respuesta
    struct Match {
        let score:       Double   // 0.0 – 1.0 (confianza del match)
        let title:       String
        let artist:      String
        let duration:    Int      // segundos (de MusicBrainz)
        let recordingId: String   // MusicBrainz Recording ID (usamos como ISRC proxy)
    }

    // Decodificación interna del JSON de AcousticID
    private struct Response: Decodable {
        let status:  String
        let results: [Result]?

        struct Result: Decodable {
            let id:         String
            let score:      Double
            let recordings: [Recording]?

            struct Recording: Decodable {
                let id:       String
                let title:    String?
                let duration: Int?
                let artists:  [Artist]?

                struct Artist: Decodable {
                    let name: String?
                }
            }
        }
    }

    // MARK: - Lookup
    /// Envía fingerprint a AcousticID y retorna el mejor match (score > umbral).
    /// Se ejecuta en el hilo que lo llame — usar en background queue.
    static func lookup(fingerprint: String,
                       duration: Int,
                       apiKey: String,
                       scoreThreshold: Double = 0.65,
                       completion: @escaping (Match?) -> Void) {

        guard !apiKey.isEmpty else {
            print("[AcousticID] API key no configurada")
            completion(nil)
            return
        }

        var components = URLComponents(string: apiURL)!
        components.queryItems = [
            URLQueryItem(name: "client",      value: apiKey),
            URLQueryItem(name: "meta",        value: "recordings"),
            URLQueryItem(name: "fingerprint", value: fingerprint),
            URLQueryItem(name: "duration",    value: "\(duration)"),
        ]

        guard let url = components.url else { completion(nil); return }

        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                print("[AcousticID] Error de red: \(error.localizedDescription)")
                completion(nil)
                return
            }
            guard let data = data else { completion(nil); return }

            do {
                let decoded = try JSONDecoder().decode(Response.self, from: data)

                guard decoded.status == "ok",
                      let results = decoded.results,
                      let best = results.max(by: { $0.score < $1.score }),
                      best.score >= scoreThreshold,
                      let recording = best.recordings?.first else {
                    print("[AcousticID] Sin match (status: \(decoded.status), resultados: \(decoded.results?.count ?? 0))")
                    completion(nil)
                    return
                }

                let title  = recording.title  ?? ""
                let artist = recording.artists?.first?.name ?? ""
                let dur    = recording.duration ?? duration

                guard !title.isEmpty else { completion(nil); return }

                let match = Match(
                    score:       best.score,
                    title:       title,
                    artist:      artist,
                    duration:    dur,
                    recordingId: recording.id
                )
                print("[AcousticID] ✅ Match: \(artist) - \(title) (score: \(String(format: "%.2f", best.score)))")
                completion(match)

            } catch {
                print("[AcousticID] Error parseando respuesta: \(error)")
                if let raw = String(data: data, encoding: .utf8) {
                    print("[AcousticID] Raw: \(raw.prefix(300))")
                }
                completion(nil)
            }
        }.resume()
    }
}
