import Foundation

class APIClient {
    static let shared = APIClient()

    private let session = URLSession.shared
    private var baseURL: String { ConfigManager.shared.config.apiBaseURL }
    private var token:   String { ConfigManager.shared.config.sessionToken }

    private init() {}

    // MARK: - Autenticación
    struct LoginRequest: Encodable {
        let idLocal: String
        let password: String
        enum CodingKeys: String, CodingKey {
            case idLocal = "id_local"
            case password
        }
    }

    struct LoginResponse: Decodable {
        let ok:           Bool
        let sessionToken: String?
        let nombreLocal:  String?
        enum CodingKeys: String, CodingKey {
            case ok
            case sessionToken = "session_token"
            case nombreLocal  = "nombre_local"
        }
    }

    func login(idLocal: String,
               password: String,
               completion: @escaping (Result<LoginResponse, Error>) -> Void) {

        guard let url = URL(string: "\(baseURL)/v1/login") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONEncoder().encode(LoginRequest(idLocal: idLocal, password: password))
        req.timeoutInterval = 15

        session.dataTask(with: req) { data, _, error in
            if let error = error { completion(.failure(error)); return }
            guard let data = data else {
                completion(.failure(NSError(domain: "APIClient", code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "Sin datos"])))
                return
            }
            do {
                let resp = try JSONDecoder().decode(LoginResponse.self, from: data)
                completion(.success(resp))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }

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

        guard let url = URL(string: "\(baseURL)/v1/plays") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // El servidor autentica con X-Session-Token (no Bearer)
        req.setValue(token,              forHTTPHeaderField: "X-Session-Token")
        req.httpBody = try? JSONEncoder().encode(PlaysPayload(plays: plays))
        req.timeoutInterval = 30

        session.dataTask(with: req) { data, response, error in
            if let error = error { completion(.failure(error)); return }
            guard let data = data else {
                completion(.failure(NSError(domain: "APIClient", code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "Sin datos"])))
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
}
