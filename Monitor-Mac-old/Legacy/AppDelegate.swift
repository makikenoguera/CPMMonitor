import AppKit
import SwiftUI
import Combine

class AppDelegate: NSObject, NSApplicationDelegate {

    // MARK: - Core Services
    let configManager      = ConfigManager.shared
    let dbManager          = DatabaseManager.shared
    let apiClient          = APIClient.shared
    let scannerManager     = ScannerManager.shared
    let syncManager        = SyncManager.shared
    let permissionManager  = PermissionManager.shared

    // MARK: - UI
    private var menuBarManager: MenuBarManager?
    var panelController: PanelController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        dbManager.initializeDatabase()

        // Sincronizar launchAtLogin: si el config lo pide, registrar con el sistema.
        // LaunchAtLoginManager es idempotente (seguro llamar en cada arranque).
        LaunchAtLoginManager.setEnabled(configManager.config.launchAtLogin)

        // Construir barra de menú
        menuBarManager = MenuBarManager(
            onOpenPanel: { [weak self] in self?.togglePanel() },
            onQuit:      { NSApp.terminate(nil) }
        )

        // Iniciar scanner si ya hay configuración
        if configManager.isActivated {
            scannerManager.start()
            syncManager.start()
            menuBarManager?.updateStatus(.connected)
        } else {
            showPanel()
        }

        // Solicitar todos los permisos de automatización al arrancar
        // macOS muestra el diálogo para cada app que no haya aprobado aún
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.permissionManager.requestAllPermissions()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        scannerManager.stop()
        syncManager.stop()
    }

    // MARK: - Panel
    func togglePanel() {
        if panelController?.window?.isVisible == true {
            panelController?.close()
        } else {
            showPanel()
        }
    }

    func showPanel() {
        if panelController == nil {
            panelController = PanelController()
        }
        panelController?.showPanel()
    }

    // MARK: - Activación completada
    func didActivate() {
        scannerManager.start()
        syncManager.start()
        menuBarManager?.updateStatus(.connected)
        // Verificar permisos después de activar
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            PermissionManager.shared.requestAllPermissions()
        }
    }
}
