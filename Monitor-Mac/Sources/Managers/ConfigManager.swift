import Foundation
import Combine

class ConfigManager: ObservableObject {
    static let shared = ConfigManager()

    private let key    = "sumartered_config"
    private let oldKey = "cpm_config"           // legacy key — migration only, to be removed
    private let defaults = UserDefaults.standard

    @Published var config: AppConfig {
        didSet { save() }
    }

    var isActivated: Bool {
        !config.venueId.isEmpty && !config.apiKey.isEmpty
    }

    private init() {
        // Intentar cargar desde la clave actual
        if let data = defaults.data(forKey: key),
           let decoded = try? JSONDecoder().decode(AppConfig.self, from: data) {
            config = decoded
        // Migración desde clave anterior
        } else if let data = defaults.data(forKey: oldKey),
                  let decoded = try? JSONDecoder().decode(AppConfig.self, from: data) {
            config = decoded
            // Guardar bajo la nueva clave y eliminar la antigua
            if let newData = try? JSONEncoder().encode(decoded) {
                defaults.set(newData, forKey: key)
            }
            defaults.removeObject(forKey: oldKey)
            print("[Config] Migrada configuración de '\(oldKey)' → '\(key)'")
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
