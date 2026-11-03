import SwiftUI
import AppKit

@main
struct SumarteRedMonitorApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        // Sin ventana principal — solo barra de menú (LSUIElement = true)
        Settings {
            EmptyView()
        }
    }
}
