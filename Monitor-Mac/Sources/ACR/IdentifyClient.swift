import Foundation

/// Cliente HTTP para el endpoint de identificación de SumarteRed.
/// Envía fingerprint Chromaprint al servidor propio en lugar de llamar AcousticID directamente.
///
/// El servidor maneja:
///   1. Consulta a AcousticID (con la API key del servidor)
///   2. Validación contra el catálogo SumarteRed (fingerprints.db migrado a PostgreSQL)
///   3. Devolución del ISRC real (no el UUID de MusicBrainz)
///   4. Flag `in_catalog` para saber si cuenta para regalías
///
/// Endpoint: POST /v1/identify
/// Auth: X-API-Key: <venue_api_key>
struct IdentifyClient {

    // MARK: - Modelo de respuesta
    struct IdentifyResult {
        let artista:    String
        let titulo:     String
        let duracion:   Int      // segundos
        let isrc:       String   // ISRC real ej: "CO-ABC-23-00001" (o "" si no hay)
        let isrcFuente: String   // "sumartered" | "acoustid" | ""
        let inCatalog:  Bool     // true si la canción está en el catálogo SumarteRed
        let confianza:  Double   // 0.0 – 1.0
    }

    // Decodificación del JSON del servidor
    private struct Response: Decodable {
        let matched:    Bool
        let artista:    String?
        let titulo:     String?
        let duracion:   Int?
        let isrc:       String?
        let isrcFuente: String?
        let inCatalog:  Bool?
        let confianza:  Double?
        let error:      String?

        enum CodingKeys: String, CodingKey {
            case matched, artista, titulo, duracion, isrc
            case isrcFuente  = "isrc_fuente"
            case inCatalog   = "in_catalog"
            case confianza, error
        }
    }

    // MARK: - Lookup
    /// Envía fingerprint al servidor y retorna el resultado de identificación.
    /// Se ejecuta en el hilo que lo llame — usar en background queue.
    static func lookup(fingerprint: String,
                       duration: Int,
                       serverURL: String,
                       venueId: String,
                       apiKey: String,
                       completion: @escaping (IdentifyResult?) -> Void) {

        guard !apiKey.isEmpty, !venueId.isEmpty else {
            print("[Identify] Venue no configurado — falta venueId o apiKey")
            completion(nil)
            return
        }

        guard let url = URL(string: "\(serverURL)/v1/identify") else {
            print("[Identify] URL inválida: \(serverURL)/v1/identify")
            completion(nil)
            return
        }

        // Payload
        let body: [String: Any] = [
            "fingerprint": fingerprint,
            "duration":    duration,
            "venue_id":    venueId
        ]

        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else {
            completion(nil)
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey,             forHTTPHeaderField: "X-API-Key")
        request.httpBody = bodyData
        request.timeoutInterval = 20

        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("[Identify] Error de red: \(error.localizedDescription)")
                completion(nil)
                return
            }

            // Logging del status HTTP
            if let http = response as? HTTPURLResponse {
                if http.statusCode == 401 {
                    print("[Identify] ⚠️  API key inválida o venue no autorizado (401)")
                    completion(nil)
                    return
                }
                if http.statusCode != 200 {
                    print("[Identify] ⚠️  Status HTTP \(http.statusCode)")
                }
            }

            guard let data = data else { completion(nil); return }

            do {
                let decoded = try JSONDecoder().decode(Response.self, from: data)

                guard decoded.matched,
                      let artista   = decoded.artista, !artista.isEmpty,
                      let titulo    = decoded.titulo,  !titulo.isEmpty,
                      let confianza = decoded.confianza else {
                    print("[Identify] Sin match: \(decoded.error ?? "sin detalles")")
                    completion(nil)
                    return
                }

                let result = IdentifyResult(
                    artista:    artista,
                    titulo:     titulo,
                    duracion:   decoded.duracion ?? duration,
                    isrc:       decoded.isrc       ?? "",
                    isrcFuente: decoded.isrcFuente ?? "",
                    inCatalog:  decoded.inCatalog  ?? false,
                    confianza:  confianza
                )

                let catalogTag = result.inCatalog ? "✅ en catálogo" : "⚠️  fuera de catálogo"
                print("[Identify] \(catalogTag): \(artista) - \(titulo) (confianza: \(String(format: "%.2f", confianza)), ISRC: \(result.isrc.isEmpty ? "—" : result.isrc))")
                completion(result)

            } catch {
                print("[Identify] Error parseando respuesta: \(error)")
                if let raw = String(data: data, encoding: .utf8) {
                    print("[Identify] Raw: \(raw.prefix(400))")
                }
                completion(nil)
            }
        }.resume()
    }
}
