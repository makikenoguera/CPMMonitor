import SwiftUI

/// Pantalla de activación del venue.
/// v3.0: usa venueId + apiKey (no hay usuario/contraseña).
/// El admin del sistema entrega estos valores al venue en el onboarding.
struct SetupView: View {
    @StateObject private var config = ConfigManager.shared

    @State private var venueId     = ""
    @State private var apiKey      = ""
    @State private var serverURL   = "https://monitor.sumartered.com"
    @State private var showApiKey  = false
    @State private var showServer  = false
    @State private var isLoading   = false
    @State private var loadingMsg  = ""
    @State private var errorMsg    = ""

    var body: some View {
        VStack(spacing: 0) {

            // Header
            VStack(spacing: 6) {
                Image(systemName: "waveform.badge.magnifyingglass")
                    .font(.system(size: 44))
                    .foregroundColor(.accentColor)
                Text("SumarteRed Monitor")
                    .font(.title.bold())
                Text("Activa tu venue para comenzar a monitorear")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
            .padding(.top, 36)
            .padding(.bottom, 28)

            // Formulario
            VStack(alignment: .leading, spacing: 16) {

                // Venue ID
                VStack(alignment: .leading, spacing: 4) {
                    Text("ID del Venue").font(.caption).foregroundColor(.secondary)
                    TextField("Ej: VENUE-001", text: $venueId)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                }

                // API Key
                VStack(alignment: .leading, spacing: 4) {
                    Text("API Key").font(.caption).foregroundColor(.secondary)
                    HStack(spacing: 6) {
                        Group {
                            if showApiKey {
                                TextField("API Key del venue", text: $apiKey)
                            } else {
                                SecureField("API Key del venue", text: $apiKey)
                            }
                        }
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                        .font(.system(.body, design: .monospaced))

                        Button { showApiKey.toggle() } label: {
                            Image(systemName: showApiKey ? "eye.slash" : "eye")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    Text("Tu administrador te entrega estos datos.")
                        .font(.caption2).foregroundColor(.secondary)
                }

                // Servidor (avanzado, colapsable)
                DisclosureGroup(isExpanded: $showServer) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("URL del servidor").font(.caption).foregroundColor(.secondary)
                        TextField("https://monitor.sumartered.com", text: $serverURL)
                            .textFieldStyle(.roundedBorder)
                            .autocorrectionDisabled()
                    }
                    .padding(.top, 8)
                } label: {
                    Text("Configuración avanzada")
                        .font(.caption).foregroundColor(.secondary)
                }

                // Estado / Error
                if !loadingMsg.isEmpty {
                    HStack(spacing: 6) {
                        ProgressView().scaleEffect(0.6)
                        Text(loadingMsg).font(.caption).foregroundColor(.secondary)
                    }
                } else if !errorMsg.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red).font(.caption)
                        Text(errorMsg).font(.caption).foregroundColor(.red)
                    }
                }

                // Botón activar
                Button(action: activate) {
                    HStack {
                        if isLoading { ProgressView().scaleEffect(0.75) }
                        Text(isLoading ? "Verificando…" : "Activar venue")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(venueId.trimmingCharacters(in: .whitespaces).isEmpty
                          || apiKey.trimmingCharacters(in: .whitespaces).isEmpty
                          || isLoading)
            }
            .padding(.horizontal, 32)

            Spacer()

            Text("monitor.sumartered.com")
                .font(.caption2).foregroundColor(.secondary)
                .padding(.bottom, 20)
        }
        .frame(width: 380, height: 500)
    }

    // MARK: - Activar
    private func activate() {
        isLoading = true
        errorMsg  = ""
        loadingMsg = ""

        let vId  = venueId.trimmingCharacters(in: .whitespaces)
        let aKey = apiKey.trimmingCharacters(in: .whitespaces)
        let sURL = serverURL.trimmingCharacters(in: .whitespaces).isEmpty
                 ? "https://monitor.sumartered.com"
                 : serverURL.trimmingCharacters(in: .whitespaces)

        APIClient.shared.verifyVenue(venueId: vId, apiKey: aKey, serverURL: sURL) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let resp):
                    if resp.ok {
                        config.config.venueId     = vId
                        config.config.apiKey      = aKey
                        config.config.serverURL   = sURL
                        config.config.nombreLocal = resp.nombreLocal ?? vId

                        // Mostrar progreso de descarga del catálogo
                        loadingMsg = "Descargando catálogo de canciones…"

                        // Arrancar servicios y esperar a que el catálogo esté listo
                        (NSApp.delegate as? AppDelegate)?.didActivate()

                        // Dar tiempo al catálogo para iniciar la descarga (primer sync)
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                            isLoading  = false
                            loadingMsg = ""
                            // RootView detecta isActivated == true y cambia a ContentView
                        }
                    } else {
                        isLoading = false
                        errorMsg  = "Venue ID o API Key incorrectos."
                    }

                case .failure(let err):
                    isLoading = false
                    if case APIClient.APIError.unauthorized = err {
                        errorMsg = "API Key inválida. Verifica con tu administrador."
                    } else {
                        errorMsg = "Sin conexión al servidor. Verifica la URL y la red."
                    }
                }
            }
        }
    }
}

#Preview {
    SetupView()
}
