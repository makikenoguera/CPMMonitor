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
        // Forzar dark mode en el panel — el diseño (cards oscuras, header celeste,
        // texto blanco) está pensado para dark. NSColor adaptativos (controlBackground,
        // secondary, etc.) se resuelven en sus variantes oscuras con .darkAqua.
        panel.appearance = NSAppearance(named: .darkAqua)
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
