import AppKit

enum MenuStatus {
    case connected
    case disconnected
    case syncing
}

class MenuBarManager {
    private var statusItem: NSStatusItem?
    private var onOpenPanel: () -> Void
    private var onQuit:      () -> Void
    private var currentStatus: MenuStatus = .disconnected

    // Menu items
    private var statusMenuItem: NSMenuItem?
    private var pendingMenuItem: NSMenuItem?

    init(onOpenPanel: @escaping () -> Void, onQuit: @escaping () -> Void) {
        self.onOpenPanel = onOpenPanel
        self.onQuit      = onQuit
        buildStatusItem()
    }

    // MARK: - Build
    private func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)

        if let button = statusItem?.button {
            button.image = iconImage(connected: false)
            button.toolTip = "SumarteRed Monitor"
        }

        let menu = NSMenu()

        // Título / estado
        let titleItem = NSMenuItem(title: "SumarteRed Monitor", action: nil, keyEquivalent: "")
        titleItem.isEnabled = false
        menu.addItem(titleItem)

        let statusItem2 = NSMenuItem(title: "Desconectado", action: nil, keyEquivalent: "")
        statusItem2.isEnabled = false
        self.statusMenuItem = statusItem2
        menu.addItem(statusItem2)

        menu.addItem(NSMenuItem.separator())

        // Pendientes
        let pendItem = NSMenuItem(title: "Pendientes: —", action: nil, keyEquivalent: "")
        pendItem.isEnabled = false
        self.pendingMenuItem = pendItem
        menu.addItem(pendItem)

        menu.addItem(NSMenuItem.separator())

        // Abrir panel
        let openItem = NSMenuItem(title: "Abrir SumarteRed Monitor…",
                                  action: #selector(handleOpenPanel),
                                  keyEquivalent: "")
        openItem.target = self
        menu.addItem(openItem)

        menu.addItem(NSMenuItem.separator())

        // Sync manual
        let syncItem = NSMenuItem(title: "Sincronizar ahora",
                                  action: #selector(handleSync),
                                  keyEquivalent: "")
        syncItem.target = self
        menu.addItem(syncItem)

        menu.addItem(NSMenuItem.separator())

        // Salir
        let quitItem = NSMenuItem(title: "Salir",
                                  action: #selector(handleQuit),
                                  keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        self.statusItem?.menu = menu
    }

    // MARK: - Acciones
    @objc private func handleOpenPanel() { onOpenPanel() }
    @objc private func handleQuit()      { onQuit() }
    @objc private func handleSync()      { SyncManager.shared.syncPending() }

    // MARK: - Actualizar estado
    func updateStatus(_ status: MenuStatus) {
        currentStatus = status
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            let connected = status == .connected || status == .syncing
            self.statusItem?.button?.image = self.iconImage(connected: connected)
            switch status {
            case .connected:    self.statusMenuItem?.title = "Conectado ✓"
            case .disconnected: self.statusMenuItem?.title = "Desconectado"
            case .syncing:      self.statusMenuItem?.title = "Sincronizando…"
            }
        }
    }

    func updatePendingCount(_ count: Int) {
        DispatchQueue.main.async { [weak self] in
            self?.pendingMenuItem?.title = count > 0
                ? "Pendientes: \(count)"
                : "Sin pendientes"
        }
    }

    // MARK: - Icono
    private func iconImage(connected: Bool) -> NSImage? {
        let name = connected ? "waveform.badge.checkmark" : "waveform"
        let symConfig = NSImage.SymbolConfiguration(pointSize: 15, weight: .medium)
        guard let image = NSImage(systemSymbolName: name, accessibilityDescription: "SumarteRed Monitor")?
            .withSymbolConfiguration(symConfig) else { return nil }
        image.isTemplate = true  // blanco/negro automático según el tema del sistema
        return image
    }
}
