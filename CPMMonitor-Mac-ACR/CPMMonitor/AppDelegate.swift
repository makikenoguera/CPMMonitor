import AppKit
import SwiftUI
import Combine

class AppDelegate: NSObject, NSApplicationDelegate {

    // MARK: - Core Services
    let configManager  = ConfigManager.shared
    let dbManager      = DatabaseManager.shared
    let apiClient      = APIClient.shared
    let scannerManager = ScannerManager.shared
    let syncManager    = SyncManager.shared

    // MARK: - UI
    private var menuBarManager: MenuBarManager?
    var panelController: PanelController?

    func applicationWillFinishLaunching(_ notification: Notification) {
        // Instancia única: si ya hay una copia corriendo, activarla y terminar esta.
        let bundleId = Bundle.main.bundleIdentifier ?? ""
        let others = NSRunningApplication.runningApplications(withBundleIdentifier: bundleId)
            .filter { !$0.isCurrentApplication }
        if !others.isEmpty {
            others.first?.activate(options: .activateIgnoringOtherApps)
            NSApp.terminate(nil)
        }
    }

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

        // El permiso de Screen Recording lo solicita ACRScanner al iniciar la captura.
        // No hay permisos de AppleEvents — el sistema ACR es 100% loopback.
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
    }
}
