import SwiftUI

/// Vista raíz: cambia automáticamente entre SetupView y ContentView
/// cuando ConfigManager.isActivated cambia.
struct RootView: View {
    @ObservedObject private var config = ConfigManager.shared

    var body: some View {
        let accentCeleste = Color(red: 0.23, green: 0.72, blue: 0.82)
        let bgCeleste     = Color(red: 0.94, green: 0.98, blue: 0.98)
        if config.isActivated {
            ContentView()
                .background(bgCeleste)
                .accentColor(accentCeleste)
                .tint(accentCeleste)
                .colorScheme(.light)
        } else {
            SetupView()
                .background(bgCeleste)
                .accentColor(accentCeleste)
                .tint(accentCeleste)
                .colorScheme(.light)
        }
    }
}
