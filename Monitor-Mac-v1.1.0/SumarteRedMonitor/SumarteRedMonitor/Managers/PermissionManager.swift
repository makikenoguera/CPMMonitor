import Foundation
import AppKit
import Combine

class PermissionManager: ObservableObject {
    static let shared = PermissionManager()

    enum PermissionStatus: String {
        case granted       = "Permitido"
        case denied        = "Denegado"
        case notDetermined = "Sin verificar"
        case appNotRunning = "App no abierta"
    }

    struct AppPermission: Identifiable {
        let id: String            // "spotify", "applemusic", etc.
        let displayName: String   // nombre en UI
        let processName: String   // como aparece en NSWorkspace
        let bundleId: String      // para lanzar la app
        let testScript: String    // AppleScript de prueba (benigno)
        var status: PermissionStatus = .notDetermined
    }

    @Published var permissions: [AppPermission] = [
        AppPermission(
            id: "spotify", displayName: "Spotify",
            processName: "Spotify", bundleId: "com.spotify.client",
            testScript: "tell application \"Spotify\" to return name"
        ),
        AppPermission(
            id: "applemusic", displayName: "Apple Music",
            processName: "Music", bundleId: "com.apple.Music",
            testScript: "tell application \"Music\" to return name"
        ),
        AppPermission(
            id: "chrome", displayName: "Google Chrome",
            processName: "Google Chrome", bundleId: "com.google.Chrome",
            testScript: "tell application \"Google Chrome\" to return name"
        ),
        AppPermission(
            id: "safari", displayName: "Safari",
            processName: "Safari", bundleId: "com.apple.Safari",
            testScript: "tell application \"Safari\" to return name"
        ),
    ]

    private init() {}

    // MARK: - Verificar todos los permisos
    func checkAll() {
        for i in 0..<permissions.count {
            permissions[i].status = checkStatus(permissions[i])
        }
    }

    private func checkStatus(_ perm: AppPermission) -> PermissionStatus {
        guard AppleScriptRunner.isRunning(perm.processName) else {
            return .appNotRunning
        }
        let result = AppleScriptRunner.runCheckingError(perm.testScript)
        switch result {
        case .success:   return .granted
        case .denied:    return .denied
        case .unknown:   return .notDetermined
        }
    }

    // MARK: - Solicitar permiso (dispara diálogo de macOS si no estaba concedido)
    func requestPermission(for id: String) {
        guard let idx = permissions.firstIndex(where: { $0.id == id }) else { return }
        let perm = permissions[idx]

        // Si la app no está corriendo, la lanzamos primero
        if !AppleScriptRunner.isRunning(perm.processName) {
            if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: perm.bundleId) {
                NSWorkspace.shared.open(url)
                // Esperar un momento a que arranque antes de pedir permiso
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
                    _ = AppleScriptRunner.run(perm.testScript)
                    self?.refreshStatus(idx)
                }
            }
        } else {
            _ = AppleScriptRunner.run(perm.testScript)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
                self?.refreshStatus(idx)
            }
        }
    }

    private func refreshStatus(_ idx: Int) {
        permissions[idx].status = checkStatus(permissions[idx])
    }

    // MARK: - Solicitar todos (primer arranque)
    func requestAllPermissions() {
        for perm in permissions {
            if AppleScriptRunner.isRunning(perm.processName) {
                _ = AppleScriptRunner.run(perm.testScript)
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            self?.checkAll()
        }
    }

    // MARK: - Abrir Ajustes del Sistema → Automatización
    func openAutomationSettings() {
        NSWorkspace.shared.open(
            URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")!
        )
    }

    // MARK: - ¿Todos los permisos esenciales concedidos?
    var allEssentialGranted: Bool {
        let essential = ["spotify", "chrome"]
        return essential.allSatisfy { id in
            permissions.first(where: { $0.id == id })?.status == .granted
        }
    }
}
