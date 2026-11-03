import Foundation
import Combine

class ConfigManager: ObservableObject {
    static let shared = ConfigManager()

    private let key = "cpm_config"
    private let defaults = UserDefaults.standard

    @Published var config: AppConfig {
        didSet { save() }
    }

    var isActivated: Bool {
        !config.idLocal.isEmpty && !config.sessionToken.isEmpty
    }

    private init() {
        if let data = defaults.data(forKey: key),
           let decoded = try? JSONDecoder().decode(AppConfig.self, from: data) {
            config = decoded
        } else {
            config = AppConfig()
        }
    }

    func save() {
        if let data = try? JSONEncoder().encode(config) {
            defaults.set(data, forKey: key)
        }
    }

    func reset() {
        config = AppConfig()
        defaults.removeObject(forKey: key)
    }
}
