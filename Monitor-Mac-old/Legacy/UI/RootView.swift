import SwiftUI

/// Vista raíz: cambia automáticamente entre SetupView y ContentView
/// cuando ConfigManager.isActivated cambia.
struct RootView: View {
    @ObservedObject private var config = ConfigManager.shared

    var body: some View {
        if config.isActivated {
            ContentView()
        } else {
            SetupView()
        }
    }
}
