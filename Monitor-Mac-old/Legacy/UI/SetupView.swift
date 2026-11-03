import SwiftUI
import AppKit

struct SetupView: View {
    @StateObject private var config = ConfigManager.shared

    @State private var idLocal      = ""
    @State private var password     = ""
    @State private var showPassword = false
    @State private var isLoading    = false
    @State private var errorMsg     = ""

    var body: some View {
        VStack(spacing: 0) {

            // Header
            VStack(spacing: 6) {
                Image(systemName: "music.note.list")
                    .font(.system(size: 40))
                    .foregroundColor(.accentColor)
                Text("CPM Monitor")
                    .font(.title.bold())
                Text("Activa tu local para comenzar a ganar")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            .padding(.top, 36)
            .padding(.bottom, 28)

            // Formulario
            VStack(alignment: .leading, spacing: 16) {

                VStack(alignment: .leading, spacing: 4) {
                    Text("ID de Local").font(.caption).foregroundColor(.secondary)
                    TextField("Ej: LOCAL-001", text: $idLocal)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Contraseña").font(.caption).foregroundColor(.secondary)
                    HStack(spacing: 6) {
                        Group {
                            if showPassword {
                                TextField("Contraseña", text: $password)
                            } else {
                                SecureField("Contraseña", text: $password)
                            }
                        }
                        .textFieldStyle(.roundedBorder)

                        Button {
                            showPassword.toggle()
                        } label: {
                            Image(systemName: showPassword ? "eye.slash" : "eye")
                                .foregroundColor(.secondary)
                                .frame(width: 20, height: 20)
                        }
                        .buttonStyle(.plain)
                        .help(showPassword ? "Ocultar contraseña" : "Mostrar contraseña")
                    }
                }

                if !errorMsg.isEmpty {
                    Text(errorMsg)
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding(.top, 2)
                }

                Button(action: activate) {
                    HStack {
                        if isLoading {
                            ProgressView().scaleEffect(0.7)
                        }
                        Text(isLoading ? "Verificando…" : "Activar")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(idLocal.trimmingCharacters(in: .whitespaces).isEmpty
                          || password.isEmpty
                          || isLoading)
            }
            .padding(.horizontal, 32)

            Spacer()

            // Footer
            Text("monitor.cpmtracks.com")
                .font(.caption2)
                .foregroundColor(.secondary)
                .padding(.bottom, 20)
        }
        .frame(width: 360, height: 420)
    }

    // MARK: - Activar
    private func activate() {
        isLoading = true
        errorMsg  = ""
        let idTrimmed = idLocal.trimmingCharacters(in: .whitespaces)

        APIClient.shared.login(idLocal: idTrimmed, password: password) { result in
            DispatchQueue.main.async {
                isLoading = false
                switch result {
                case .success(let resp):
                    if resp.ok, let token = resp.sessionToken {
                        // Guardar config — RootView cambia automáticamente a ContentView
                        config.config.idLocal      = idTrimmed
                        config.config.sessionToken = token
                        config.config.nombreLocal  = resp.nombreLocal ?? ""
                        // Arrancar scanner y sync
                        (NSApp.delegate as? AppDelegate)?.didActivate()
                    } else {
                        errorMsg = "Credenciales incorrectas. Verifica tu ID y contraseña."
                    }
                case .failure(let err):
                    errorMsg = "Error de conexión: \(err.localizedDescription)"
                }
            }
        }
    }
}

#Preview {
    SetupView()
}
