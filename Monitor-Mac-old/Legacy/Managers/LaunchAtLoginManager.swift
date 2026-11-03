import Foundation
import ServiceManagement

/// Registra / desregistra la app para que arranque al iniciar sesión.
///
/// - macOS 13+: usa `SMAppService.mainApp` (sin helper bundle).
/// - macOS 12:  escribe / borra un LaunchAgent plist en ~/Library/LaunchAgents/.
enum LaunchAtLoginManager {

    // MARK: - API pública

    static func setEnabled(_ enabled: Bool) {
        if #available(macOS 13.0, *) {
            setViaSMAppService(enabled)
        } else {
            setViaLaunchAgent(enabled)
        }
    }

    static func isEnabled() -> Bool {
        if #available(macOS 13.0, *) {
            return SMAppService.mainApp.status == .enabled
        } else {
            return FileManager.default.fileExists(atPath: plistURL.path)
        }
    }

    // MARK: - macOS 13+ (SMAppService)

    @available(macOS 13.0, *)
    private static func setViaSMAppService(_ enabled: Bool) {
        do {
            if enabled {
                // register() es idempotente; solo llama si no está ya registrado
                if SMAppService.mainApp.status != .enabled {
                    try SMAppService.mainApp.register()
                    print("[LaunchAtLogin] Registrado con SMAppService")
                }
            } else {
                try SMAppService.mainApp.unregister()
                print("[LaunchAtLogin] Desregistrado con SMAppService")
            }
        } catch {
            // Error común en desarrollo (app no instalada en /Applications).
            // En producción, con la app en /Applications, funciona correctamente.
            print("[LaunchAtLogin] SMAppService error: \(error.localizedDescription)")
        }
    }

    // MARK: - macOS 12 (LaunchAgent plist)

    private static var plistURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/com.cpmtracks.monitor.plist")
    }

    private static func setViaLaunchAgent(_ enabled: Bool) {
        let fm  = FileManager.default
        let url = plistURL
        if enabled {
            guard let execPath = Bundle.main.executablePath else { return }
            let plist: [String: Any] = [
                "Label":            "com.cpmtracks.monitor",
                "ProgramArguments": [execPath],
                "RunAtLoad":        true,
                "KeepAlive":        false
            ]
            try? fm.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            NSDictionary(dictionary: plist).write(toFile: url.path, atomically: true)
            print("[LaunchAtLogin] Plist escrito: \(url.path)")
        } else {
            try? fm.removeItem(at: url)
            print("[LaunchAtLogin] Plist eliminado")
        }
    }
}
