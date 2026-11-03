import SwiftUI

struct ContentView: View {
    @StateObject private var config      = ConfigManager.shared
    @StateObject private var scanner     = ScannerManager.shared
    @StateObject private var permissions = PermissionManager.shared

    @State private var history: [PlayRecord] = []
    @State private var pendingCount: Int = 0
    @State private var refreshTimer: Timer?
    @State private var selectedTab = 0

    var body: some View {
        VStack(spacing: 0) {

            // MARK: Header
            headerBar

            Divider()

            // MARK: Now Playing
            nowPlayingCard
                .padding(.horizontal, 16)
                .padding(.top, 14)

            Divider().padding(.horizontal, 16).padding(.top, 12)

            // MARK: Tabs
            Picker("", selection: $selectedTab) {
                Text("Historial").tag(0)
                Text("Configuración").tag(1)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            if selectedTab == 0 {
                historyList
            } else {
                settingsView
            }

            Spacer(minLength: 0)
        }
        .frame(width: 460, height: 620)
        .onAppear {
            loadHistory()
            startRefresh()
            permissions.checkAll()
        }
        .onDisappear {
            refreshTimer?.invalidate()
        }
    }

    // MARK: - Header
    private var headerBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("CPM Monitor")
                    .font(.headline)
                Text(config.config.nombreLocal.isEmpty ? config.config.idLocal : config.config.nombreLocal)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            HStack(spacing: 8) {
                // Estado de sync
                Label("\(pendingCount) pendientes", systemImage: pendingCount > 0 ? "arrow.triangle.2.circlepath" : "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundColor(pendingCount > 0 ? .orange : .green)

                Button {
                    SyncManager.shared.syncPending()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { loadHistory() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Sincronizar ahora")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // MARK: - Now Playing
    private var nowPlayingCard: some View {
        Group {
            if let candidate = scanner.currentCandidate {
                VStack(spacing: 6) {
                    HStack {
                        Image(systemName: sourceIcon(candidate.fuente))
                            .foregroundColor(sourceColor(candidate.fuente))
                        Text("Reproduciendo ahora")
                            .font(.caption.weight(.semibold))
                            .foregroundColor(.secondary)
                        Spacer()
                        Text(candidate.duracionFormatted)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(candidate.titulo.isEmpty ? candidate.contenido : candidate.titulo)
                                .font(.subheadline.weight(.semibold))
                                .lineLimit(1)
                            Text(candidate.artista)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            // Porcentaje ESCUCHADO (segundos acumulados / duración)
                            Text(String(format: "%.0f%% oído", candidate.porcentaje))
                                .font(.subheadline.weight(.bold))
                                .foregroundColor(candidate.porcentaje >= 90 ? .green : .primary)
                            // Posición ACTUAL en el reproductor
                            if let pos = candidate.lastPlayerPosition, candidate.duracionSeg > 0 {
                                Text(posFormatted(pos) + " / " + candidate.duracionFormatted)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            } else {
                                Text(posFormatted(candidate.segundosAcumulados) + " oídos")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }

                    // Barra doble: posición (gris) y escuchado (color)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            // Fondo: posición actual en el reproductor
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.secondary.opacity(0.15))
                                .frame(height: 6)
                            // Posición real (más claro)
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.secondary.opacity(0.35))
                                .frame(width: geo.size.width * min(candidate.posicionPct / 100, 1), height: 6)
                            // Tiempo escuchado (más oscuro / color)
                            RoundedRectangle(cornerRadius: 3)
                                .fill(candidate.porcentaje >= 90 ? Color.green : Color.accentColor)
                                .frame(width: geo.size.width * min(candidate.porcentaje / 100, 1), height: 6)
                        }
                    }
                    .frame(height: 6)
                }
                .padding(12)
                .background(Color.secondary.opacity(0.08))
                .cornerRadius(10)
            } else {
                HStack {
                    Image(systemName: "pause.circle")
                        .foregroundColor(.secondary)
                    Text("Sin reproducción activa")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .padding(12)
                .background(Color.secondary.opacity(0.06))
                .cornerRadius(10)
            }
        }
    }

    // MARK: - Historial
    private var historyList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                if history.isEmpty {
                    Text("Aún no hay plays registrados")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .padding(.top, 40)
                } else {
                    // Header de columnas
                    HStack {
                        Text("CANCIÓN").frame(maxWidth: .infinity, alignment: .leading)
                        Text("HORA").frame(width: 40, alignment: .center)
                        Text("DUR.").frame(width: 46, alignment: .center)
                        Text("%").frame(width: 36, alignment: .center)
                        Text("✓").frame(width: 26, alignment: .center)
                    }
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 6)

                    Divider().padding(.horizontal, 16)

                    ForEach(history) { record in
                        historyRow(record)
                        Divider().padding(.horizontal, 16)
                    }
                }
            }
        }
    }

    private func historyRow(_ r: PlayRecord) -> some View {
        HStack(spacing: 4) {
            // Canción
            HStack(spacing: 6) {
                Image(systemName: sourceIcon(r.fuente))
                    .font(.system(size: 11))
                    .foregroundColor(sourceColor(r.fuente))
                    .frame(width: 16)
                VStack(alignment: .leading, spacing: 1) {
                    Text(r.titulo.isEmpty ? r.contenido : r.titulo)
                        .font(.system(size: 12, weight: .medium))
                        .lineLimit(1)
                    if !r.artista.isEmpty {
                        Text(r.artista)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Hora
            Text(r.horaFormatted)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .frame(width: 40, alignment: .center)

            // Duración
            Text(r.duracionFormatted)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .frame(width: 46, alignment: .center)

            // Porcentaje
            Text(r.porcentajeFormatted)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(r.ganodinero ? .green : .primary)
                .frame(width: 36, alignment: .center)

            // Enviado
            Image(systemName: r.enviado ? "checkmark.circle.fill" : "clock")
                .font(.system(size: 12))
                .foregroundColor(r.enviado ? .green : .orange)
                .frame(width: 26, alignment: .center)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    // MARK: - Configuración
    private var settingsView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {

                // ── Local ─────────────────────────────────────────────
                settingsSection(title: "Local") {
                    settingsRow(label: "ID Local", value: config.config.idLocal)
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Nombre", value: config.config.nombreLocal.isEmpty ? "—" : config.config.nombreLocal)
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Servidor", value: config.config.apiBaseURL)
                }

                // ── Permisos ──────────────────────────────────────────
                settingsSection(title: "Permisos de automatización") {
                    ForEach(Array(permissions.permissions.enumerated()), id: \.element.id) { idx, perm in
                        HStack(spacing: 10) {
                            Image(systemName: permIcon(perm.status))
                                .foregroundColor(permColor(perm.status))
                                .frame(width: 18)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(perm.displayName).font(.system(size: 13))
                                Text(perm.status.rawValue)
                                    .font(.system(size: 10))
                                    .foregroundColor(permColor(perm.status))
                            }
                            Spacer()
                            if perm.status == .denied {
                                Button("Abrir Ajustes") { permissions.openAutomationSettings() }
                                    .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(.orange)
                            } else if perm.status != .granted {
                                Button(perm.status == .appNotRunning ? "Lanzar y pedir" : "Pedir permiso") {
                                    permissions.requestPermission(for: perm.id)
                                }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(.accentColor)
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 9)
                        if idx < permissions.permissions.count - 1 { Divider().padding(.leading, 16) }
                    }
                    Divider()
                    HStack {
                        Button { permissions.requestAllPermissions() } label: {
                            Label("Solicitar todos", systemImage: "lock.shield")
                        }
                        .buttonStyle(.plain).foregroundColor(.accentColor).font(.system(size: 12))
                        Spacer()
                        Button { permissions.checkAll() } label: {
                            Image(systemName: "arrow.clockwise")
                        }
                        .buttonStyle(.plain).foregroundColor(.secondary).help("Actualizar estado")
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                }

                // ── Fuentes ───────────────────────────────────────────
                settingsSection(title: "Fuentes de detección") {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Detectar YouTube / Navegadores").font(.system(size: 13))
                            Text("Chrome necesita «Permitir JS desde Eventos de Apple» (Ver → Opciones para desarrolladores)")
                                .font(.system(size: 10)).foregroundColor(.secondary)
                        }
                        Spacer()
                        Toggle("", isOn: $config.config.enableYouTubeScanner).labelsHidden()
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                }

                // ── Detección ─────────────────────────────────────────
                settingsSection(title: "Detección") {
                    settingsRow(label: "Intervalo de scan", value: "\(String(format: "%.0f", config.config.scanInterval))s")
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Tiempo mínimo", value: "\(String(format: "%.0f", config.config.minDetectionTime))s")
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Umbral de ganancia", value: "\(String(format: "%.0f", config.config.umbralPorcentaje))%")
                }

                // ── Sistema ───────────────────────────────────────────
                settingsSection(title: "Sistema") {
                    HStack {
                        Text("Iniciar con el sistema").font(.system(size: 13))
                        Spacer()
                        Toggle("", isOn: Binding(
                            get: { config.config.launchAtLogin },
                            set: { newVal in
                                config.config.launchAtLogin = newVal
                                LaunchAtLoginManager.setEnabled(newVal)
                            }
                        )).labelsHidden()
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                }

                // ── Cerrar sesión ─────────────────────────────────────
                Button {
                    ScannerManager.shared.stop()
                    SyncManager.shared.stop()
                    ConfigManager.shared.reset()
                    (NSApp.delegate as? AppDelegate)?.panelController?.rebuild()
                } label: {
                    Label("Cerrar sesión", systemImage: "arrow.backward.square").foregroundColor(.red)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 16).padding(.vertical, 14)
            }
            .padding(.vertical, 8)
        }
    }

    // MARK: - Helpers de permisos
    private func permIcon(_ status: PermissionManager.PermissionStatus) -> String {
        switch status {
        case .granted:       return "checkmark.circle.fill"
        case .denied:        return "xmark.circle.fill"
        case .notDetermined: return "questionmark.circle"
        case .appNotRunning: return "circle.dashed"
        }
    }

    private func permColor(_ status: PermissionManager.PermissionStatus) -> Color {
        switch status {
        case .granted:       return .green
        case .denied:        return .red
        case .notDetermined: return .secondary
        case .appNotRunning: return .orange
        }
    }

    private func settingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.secondary)
                .padding(.horizontal, 16)
                .padding(.top, 14)
                .padding(.bottom, 6)

            VStack(spacing: 0) {
                content()
            }
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            .padding(.horizontal, 16)
        }
    }

    private func settingsRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 13))
            Spacer()
            Text(value)
                .font(.system(size: 13))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // MARK: - Helpers
    private func loadHistory() {
        history      = DatabaseManager.shared.fetchHistory(limit: 100)
        pendingCount = DatabaseManager.shared.countPending()
    }

    private func startRefresh() {
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
            loadHistory()
        }
    }

    private func sourceIcon(_ fuente: String) -> String {
        switch fuente {
        case "spotify":    return "music.note"
        case "applemusic": return "applelogo"
        case "youtube":    return "play.rectangle.fill"
        case "vlc":        return "video.fill"
        default:           return "music.note"
        }
    }

    private func posFormatted(_ seconds: Double) -> String {
        let m = Int(seconds) / 60
        let s = Int(seconds) % 60
        return String(format: "%d:%02d", m, s)
    }

    private func sourceColor(_ fuente: String) -> Color {
        switch fuente {
        case "spotify":    return .green
        case "applemusic": return .pink
        case "youtube":    return .red
        case "vlc":        return .orange
        default:           return .accentColor
        }
    }
}

#Preview {
    ContentView()
}
