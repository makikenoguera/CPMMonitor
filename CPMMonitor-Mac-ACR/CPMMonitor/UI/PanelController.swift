import AppKit
import SwiftUI

class PanelController: NSObject {
    private(set) var window: NSPanel?

    override init() {
        super.init()
        buildPanel()
    }

    private func buildPanel() {
        let hosting  = NSHostingView(rootView: RootView())

        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 620),
            styleMask: [.titled, .closable, .miniaturizable, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.title           = "SumarteRed Monitor"
        panel.contentView     = hosting
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.level           = .floating
        panel.delegate        = self
        // Fondo transparente: deja que NSHostingView / SwiftUI pinte su propio fondo.
        // Color(NSColor.windowBackgroundColor) en RootView se encarga del color correcto
        // tanto en dark mode como en light mode.
        panel.backgroundColor = .clear
        panel.isOpaque        = false
        self.window = panel
    }

    func showPanel() {
        window?.center()
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func close() {
        window?.orderOut(nil)
    }

    /// Reconstruir el panel (útil tras activación para cambiar a ContentView)
    func rebuild() {
        window?.close()
        window = nil
        buildPanel()
        showPanel()
    }
}

extension PanelController: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        // No terminamos la app, solo ocultamos
    }
}
