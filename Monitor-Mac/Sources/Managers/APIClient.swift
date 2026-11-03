import Foundation

/// Cliente HTTP para el servidor SumarteRed.
/// v3.0: autenticación por API key (X-API-Key header).
/// No hay login/logout — el API key del venue es permanente.
class APIClient {
    static let shared = APIClient()

    private let session = URLSession.shared
    private var baseURL: String { ConfigManager.shared.config.serverURL }
    private var apiKey:  String { ConfigManager.shared.config.apiKey }

    private init() {}

    // MARK: - Enviar plays
    struct PlaysPayload: Encodable {
        let plays: [APIPlay]
    }

    // El servidor responde: {"accepted": ["key1","key2"], "total": 2}  HTTP 201
    struct PlaysResponse: Decodable {
        let accepted: [String]?
        let total:    Int?
    }

    func sendPlays(_ plays: [APIPlay],
                   completion: @escaping (Result<PlaysResponse, Error>) -> Void) {

        guard !apiKey.isEmpty else {
            completion(.failure(APIError.notConfigured))
            return
        }

        guard let url = URL(string: "\(baseURL)/v1/plays") else {
            completion(.failure(APIError.invalidURL))
            return
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(apiKey,             forHTTPHeaderField: "X-API-Key")
        req.httpBody = try? JSONEncoder().encode(PlaysPayload(plays: plays))
        req.timeoutInterval = 30

        session.dataTask(with: req) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            if let http = response as? HTTPURLResponse, http.statusCode == 401 {
                completion(.failure(APIError.unauthorized))
                return
            }
            guard let data = data else {
                completion(.failure(APIError.noData))
                return
            }
            do {
                let resp = try JSONDecoder().decode(PlaysResponse.self, from: data)
                completion(.success(resp))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }

    // MARK: - Verificar activación
    struct VerifyResponse: Decodable {
        let ok:          Bool
        let nombreLocal: String?
        enum CodingKeys: String, CodingKey {
            case ok
            case nombreLocal = "nombre_local"
        }
    }

    /// Verifica que venueId + apiKey sean válidos.
    /// Llama a GET /v1/venue/:venueId con X-API-Key.
    func verifyVenue(venueId: String,
                     apiKey: String,
                     serverURL: String,
                     completion: @escaping (Result<VerifyResponse, Error>) -> Void) {

        guard let url = URL(string: "\(serverURL)/v1/venue/\(venueId)") else {
            completion(.failure(APIError.invalidURL))
            return
        }

        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        req.timeoutInterval = 15

        session.dataTask(with: req) { data, response, error in
            if let error = error { completion(.failure(error)); return }
            if let http = response as? HTTPURLResponse, http.statusCode == 401 {
                completion(.failure(APIError.unauthorized))
                return
            }
            guard let data = data else {
                completion(.failure(APIError.noData))
                return
            }
            do {
                let resp = try JSONDecoder().decode(VerifyResponse.self, from: data)
                completion(.success(resp))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }

    // MARK: - Errores
    enum APIError: LocalizedError {
        case notConfigured, invalidURL, unauthorized, noData

        var errorDescription: String? {
            switch self {
            case .notConfigured: return "Venue no configurado"
            case .invalidURL:    return "URL del servidor inválida"
            case .unauthorized:  return "API key inválida o expirada"
            case .noData:        return "Sin datos del servidor"
            }
        }
    }
}
