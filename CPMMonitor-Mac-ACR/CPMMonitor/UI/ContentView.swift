import SwiftUI

// MARK: - Colores corporativos SumarteRed
// Definidos aquí porque SumarteRedTheme.swift no está en el build target.
enum SRColor {
    static let celeste     = Color(red: 0.23, green: 0.72, blue: 0.82)
    static let celesteDark = Color(red: 0.17, green: 0.58, blue: 0.68)
    static let background  = Color(red: 0.94, green: 0.98, blue: 0.98)
    static let headerBg    = Color(red: 0.15, green: 0.62, blue: 0.74)
}

struct ContentView: View {
    @StateObject private var config  = ConfigManager.shared
    @StateObject private var scanner = ScannerManager.shared
    @StateObject private var acr     = ACRScanner.shared
    @StateObject private var audio   = AudioCaptureManager.shared

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
        .frame(width: 460, height: 640)
        .onAppear {
            loadHistory()
            startRefresh()
        }
        .onDisappear {
            refreshTimer?.invalidate()
        }
    }

    // MARK: - Header
    private var headerBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("SumarteRed Monitor")
                    .font(.headline)
                    .foregroundColor(.white)
                Text(config.config.nombreLocal.isEmpty ? config.config.venueId : config.config.nombreLocal)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.8))
            }
            Spacer()
            HStack(spacing: 8) {
                Label("\(pendingCount) pendientes",
                      systemImage: pendingCount > 0 ? "arrow.triangle.2.circlepath" : "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundColor(pendingCount > 0 ? .yellow : .white.opacity(0.9))

                Button {
                    SyncManager.shared.syncPending()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { loadHistory() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .foregroundColor(.white)
                }
                .buttonStyle(.plain)
                .help("Sincronizar ahora")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(SRColor.headerBg)
    }

    // MARK: - Now Playing
    private var nowPlayingCard: some View {
        Group {
            if let candidate = scanner.currentCandidate {
                VStack(spacing: 6) {
                    HStack {
                        Image(systemName: "waveform")
                            .foregroundColor(.accentColor)
                        Text("Reproduciendo ahora")
                            .font(.caption.weight(.semibold))
                            .foregroundColor(.secondary)
                        Spacer()
                        // In-catalog badge
                        if candidate.inCatalog {
                            Label("En catálogo", systemImage: "checkmark.seal.fill")
                                .font(.caption2)
                                .foregroundColor(.green)
                        } else {
                            Label("Fuera de catálogo", systemImage: "exclamationmark.circle")
                                .font(.caption2)
                                .foregroundColor(.orange)
                        }
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
                            if !candidate.isrc.isEmpty {
                                Text("ISRC: \(candidate.isrc)")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(String(format: "%.0f%% oído", candidate.porcentaje))
                                .font(.subheadline.weight(.bold))
                                .foregroundColor(candidate.porcentaje >= 80 ? .green : .primary)
                            Text(String(format: "%.0fs / \(candidate.duracionSeg > 0 ? candidate.duracionFormatted : "?")", candidate.segundosAcumulados))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    // Barra de progreso
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.secondary.opacity(0.15))
                                .frame(height: 6)
                            RoundedRectangle(cornerRadius: 3)
                                .fill(candidate.porcentaje >= 80 ? Color.green : Color.accentColor)
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
                    queryStatusView
                    Spacer()
                }
                .padding(12)
                .background(Color.secondary.opacity(0.06))
                .cornerRadius(10)
            }
        }
    }

    @ViewBuilder
    private var queryStatusView: some View {
        switch acr.lastQueryStatus {
        case .querying:
            HStack(spacing: 6) {
                ProgressView().scaleEffect(0.6)
                Text("Identificando canción…")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        case .matched(let s):
            HStack(spacing: 6) {
                Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                Text(s).font(.subheadline).lineLimit(1)
            }
        case .matchedOutOfCatalog(let s):
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.circle").foregroundColor(.orange)
                VStack(alignment: .leading, spacing: 1) {
                    Text(s).font(.subheadline).lineLimit(1)
                    Text("Fuera del catálogo SumarteRed").font(.caption2).foregroundColor(.secondary)
                }
            }
        case .noFpcalc:
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.orange)
                Text("fpcalc no instalado").font(.subheadline).foregroundColor(.orange)
            }
        case .notConfigured:
            HStack(spacing: 6) {
                Image(systemName: "key.slash").foregroundColor(.orange)
                Text("Venue no configurado").font(.subheadline).foregroundColor(.orange)
            }
        default:
            HStack(spacing: 6) {
                Image(systemName: "pause.circle").foregroundColor(.secondary)
                Text("Sin reproducción activa").font(.subheadline).foregroundColor(.secondary)
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
                    // Header
                    HStack {
                        Text("CANCIÓN").frame(maxWidth: .infinity, alignment: .leading)
                        Text("HORA").frame(width: 40, alignment: .center)
                        Text("%").frame(width: 36, alignment: .center)
                        Text("CAT").frame(width: 30, alignment: .center)
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
            VStack(alignment: .leading, spacing: 1) {
                Text(r.titulo.isEmpty ? r.contenido : r.titulo)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1)
                HStack(spacing: 4) {
                    if !r.artista.isEmpty {
                        Text(r.artista)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                    if !r.isrc.isEmpty {
                        Text("· \(r.isrc)")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Text(r.horaFormatted)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .frame(width: 40, alignment: .center)

            Text(r.porcentajeFormatted)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(r.ganodinero ? .green : .primary)
                .frame(width: 36, alignment: .center)

            // In-catalog
            Image(systemName: r.inCatalog ? "checkmark.seal.fill" : "minus.circle")
                .font(.system(size: 11))
                .foregroundColor(r.inCatalog ? .green : .secondary)
                .frame(width: 30, alignment: .center)
                .help(r.inCatalog ? "En catálogo SumarteRed" : "Fuera del catálogo")

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

                // ── Venue ─────────────────────────────────────────────
                settingsSection(title: "Venue") {
                    settingsRow(label: "ID", value: config.config.venueId)
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Nombre", value: config.config.nombreLocal.isEmpty ? "—" : config.config.nombreLocal)
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Servidor", value: config.config.serverURL)
                    Divider().padding(.leading, 16)
                    HStack {
                        Text("API Key").font(.system(size: 13))
                        Spacer()
                        Text(config.config.apiKey.isEmpty ? "—" :
                             String(repeating: "•", count: 8) + config.config.apiKey.suffix(6))
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                }

                // ── Reconocimiento Acústico ───────────────────────────
                settingsSection(title: "Reconocimiento Acústico") {
                    HStack(spacing: 10) {
                        Image(systemName: audio.isCapturing ? "waveform" : "waveform.slash")
                            .foregroundColor(audio.isCapturing ? .green : .secondary)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Captura de audio del sistema").font(.system(size: 13))
                            Text(audio.isCapturing ? "Activa — escuchando en loopback"
                                                   : permissionLabel)
                                .font(.system(size: 10))
                                .foregroundColor(audio.isCapturing ? .green : .orange)
                        }
                        Spacer()
                        if audio.permissionStatus != .granted {
                            Button(audio.permissionStatus == .denied ? "Reintentar" : "Solicitar permiso") {
                                ACRScanner.shared.start()
                            }
                            .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(.accentColor)
                        }
                        if audio.permissionStatus == .denied {
                            Button("Abrir Ajustes") { audio.openPrivacySettings() }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(.orange)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 9)

                    Divider().padding(.leading, 16)

                    HStack(spacing: 10) {
                        Image(systemName: FingerprintEngine.isAvailable ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundColor(FingerprintEngine.isAvailable ? .green : .orange)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("fpcalc (Chromaprint)").font(.system(size: 13))
                            Text(FingerprintEngine.isAvailable
                                 ? FingerprintEngine.fpcalcPath ?? ""
                                 : "No instalado — brew install chromaprint")
                                .font(.system(size: 10))
                                .foregroundColor(FingerprintEngine.isAvailable ? .secondary : .orange)
                                .lineLimit(1)
                        }
                        Spacer()
                        if !FingerprintEngine.isAvailable {
                            Button("Instalar") {
                                NSWorkspace.shared.open(URL(string: "https://formulae.brew.sh/formula/chromaprint")!)
                            }
                            .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(.accentColor)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 9)
                }

                // ── Detección ─────────────────────────────────────────
                settingsSection(title: "Detección") {
                    settingsRow(label: "Tiempo mínimo",
                                value: "\(String(format: "%.0f", config.config.minDetectionTime))s")
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Umbral de ganancia",
                                value: "\(String(format: "%.0f", config.config.umbralPorcentaje))%")
                    Divider().padding(.leading, 16)
                    settingsRow(label: "Confianza mínima",
                                value: "\(String(format: "%.0f", config.config.scoreThreshold * 100))%")
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

                // ── Desactivar ────────────────────────────────────────
                Button {
                    ScannerManager.shared.stop()
                    SyncManager.shared.stop()
                    ConfigManager.shared.reset()
                    (NSApp.delegate as? AppDelegate)?.panelController?.rebuild()
                } label: {
                    Label("Desactivar venue", systemImage: "xmark.circle")
                        .foregroundColor(.red)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 16).padding(.vertical, 14)
            }
            .padding(.vertical, 8)
        }
    }

    // MARK: - Helpers
    private var permissionLabel: String {
        switch audio.permissionStatus {
        case .unknown:  return "Permiso no solicitado — toca «Solicitar permiso»"
        case .denied:   return "Denegado — Ajustes → Privacidad → Grabación de pantalla"
        case .granted:  return "Concedido"
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
            VStack(spacing: 0) { content() }
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
                .padding(.horizontal, 16)
        }
    }

    private func settingsRow(label: String, value: String) -> some View {
        HStack {
            Text(label).font(.system(size: 13))
            Spacer()
            Text(value).font(.system(size: 13)).foregroundColor(.secondary)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
    }

    private func loadHistory() {
        history      = DatabaseManager.shared.fetchHistory(limit: 100)
        pendingCount = DatabaseManager.shared.countPending()
    }

    private func startRefresh() {
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
            loadHistory()
        }
    }
}

#Preview {
    ContentView()
}
