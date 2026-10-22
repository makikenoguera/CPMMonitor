import SwiftUI

/// Vista raíz: cambia automáticamente entre SetupView y ContentView
/// cuando ConfigManager.isActivated cambia.
struct RootView: View {
    @ObservedObject private var config = ConfigManager.shared

    var body: some View {
        let accentCeleste = Color(red: 0.23, green: 0.72, blue: 0.82)
        if config.isActivated {
            ContentView()
                .accentColor(accentCeleste)
                .tint(accentCeleste)
        } else {
            SetupView()
                .accentColor(accentCeleste)
                .tint(accentCeleste)
        }
    }
}
