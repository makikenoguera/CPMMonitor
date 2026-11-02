import SwiftUI

struct ContentView: View {
    @StateObject private var config   = ConfigManager.shared
    @StateObject private var scanner  = ScannerManager.shared
    @StateObject private var acr      = ACRScanner.shared
    @StateObject private var audio    = AudioCaptureManager.shared
    @StateObject private var catalog  = CatalogManager.shared

    @State private var history: [PlayRecord] = []
    @State private var pendingCount: Int = 0
    @State private var refreshTimer: Timer?
    @State private var selectedTab = 1
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 0) {

            // MARK: Header
            headerBar
            Divider().overlay(SRColor.border)

            // MARK: Now Playing
            nowPlayingCard
                .padding(.horizontal, 14)
                .padding(.top, 12)
                .padding(.bottom, 4)

            // MARK: Tabs (oculto en ajustes)
            if !showSettings {
                tabBar
                    .padding(.horizontal, 14)
                    .padding(.bottom, 2)
                Divider().overlay(SRColor.border)
            } else {
                Divider().overlay(SRColor.border)
            }

            // MARK: Tab Content
            Group {
                if showSettings {
                    settingsInline
                } else if selectedTab == 0 {
                    PromovidasView()
                } else if selectedTab == 1 {
                    MonitoreoView(history: history)
                } else {
                    GananciasView()
                }
            }

            Spacer(minLength: 0)
        }
        .frame(width: 580, height: 700)
        .background(SRColor.pageBg)
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
        HStack(spacing: 10) {
            // Logo-icon matching web dashboard
            ZStack {
                RoundedRectangle(cornerRadius: 7)
                    .fill(SRColor.brand)
                    .frame(width: 30, height: 30)
                Image(systemName: "waveform")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white)
            }

            VStack(alignment: .leading, spacing: 1) {
                Text("SumarteRed Monitor")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(SRColor.textPrimary)
                Text(config.config.nombreLocal.isEmpty ? config.config.venueId : config.config.nombreLocal)
                    .font(.system(size: 10))
                    .foregroundColor(SRColor.textSecond)
            }

            Spacer()

            // Pending badge
            HStack(spacing: 4) {
                Image(systemName: pendingCount > 0 ? "arrow.triangle.2.circlepath" : "checkmark.circle.fill")
                    .font(.system(size: 10))
                    .foregroundColor(pendingCount > 0 ? SRColor.venueOrange : SRColor.srGreen)
                Text(pendingCount > 0 ? "\(pendingCount) pendientes" : "Sincronizado")
                    .font(.system(size: 10))
                    .foregroundColor(pendingCount > 0 ? SRColor.venueOrange : SRColor.textSecond)
            }

            // Sync
            Button {
                SyncManager.shared.syncPending()
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) { loadHistory() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(SRColor.brand)
            }
            .buttonStyle(.plain)
            .help("Sincronizar ahora")

            // Settings
            Button { showSettings.toggle() } label: {
                Image(systemName: showSettings ? "xmark.circle.fill" : "gearshape")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(showSettings ? SRColor.brand : SRColor.textSecond)
            }
            .buttonStyle(.plain)
            .help(showSettings ? "Cerrar ajustes" : "Configuración")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(SRColor.headerBg)
    }

    // MARK: - Custom Tab Bar (dashboard style)
    private var tabBar: some View {
        HStack(spacing: 0) {
            tabButton("Promovidas", icon: "star", tag: 0)
            tabButton("Monitoreo",  icon: "waveform.and.magnifyingglass", tag: 1)
            tabButton("Ganancias",  icon: "banknote", tag: 2)
        }
        .padding(.top, 6)
    }

    private func tabButton(_ label: String, icon: String, tag: Int) -> some View {
        let selected = selectedTab == tag
        return Button { selectedTab = tag } label: {
            VStack(spacing: 4) {
                HStack(spacing: 5) {
                    Image(systemName: icon)
                        .font(.system(size: 11))
                    Text(label)
                        .font(.system(size: 12, weight: selected ? .semibold : .regular))
                }
                .foregroundColor(selected ? SRColor.brand : SRColor.textSecond)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)

                // Underline indicator
                Rectangle()
                    .fill(selected ? SRColor.brand : Color.clear)
                    .frame(height: 2)
            }
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Now Playing
    private var nowPlayingCard: some View {
        Group {
            if let candidate = scanner.currentCandidate {
                // Active playback card
                VStack(spacing: 0) {
                    // Orange top accent bar
                    Rectangle()
                        .fill(SRColor.brand)
                        .frame(height: 2)
                        .cornerRadius(1)

                    VStack(spacing: 8) {
                        HStack(spacing: 6) {
                            Text("REPRODUCIENDO AHORA")
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundColor(SRColor.textLabel)
                                .kerning(0.5)
                            Spacer()
                            if candidate.isPromovida {
                                Label("Promovida", systemImage: "star.fill")
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(SRColor.brand)
                            } else if candidate.inCatalog {
                                Label("En catálogo", systemImage: "checkmark.seal.fill")
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(SRColor.srGreen)
                            } else {
                                Label("No promovida", systemImage: "exclamationmark.circle")
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(SRColor.textLabel)
                            }
                        }

                        HStack(alignment: .center) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(candidate.titulo.isEmpty ? candidate.contenido : candidate.titulo)
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundColor(SRColor.textPrimary)
                                    .lineLimit(1)
                                HStack(spacing: 6) {
                                    Text(candidate.artista)
                                        .font(.system(size: 11))
                                        .foregroundColor(SRColor.textSecond)
                                        .lineLimit(1)
                                    if !candidate.isrc.isEmpty {
                                        Text("·")
                                            .foregroundColor(SRColor.border)
                                        Text(candidate.isrc)
                                            .font(.system(size: 10, design: .monospaced))
                                            .foregroundColor(SRColor.textLabel)
                                    }
                                }
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(String(format: "%.0f%%", candidate.porcentaje))
                                    .font(.system(size: 22, weight: .bold))
                                    .foregroundColor(candidate.porcentaje >= 80 ? SRColor.srGreen : SRColor.brand)
                                Text(String(format: "%d:%02d / %@",
                                            Int(candidate.segundosAcumulados) / 60,
                                            Int(candidate.segundosAcumulados) % 60,
                                            candidate.duracionSeg > 0 ? candidate.duracionFormatted : "?"))
                                    .font(.system(size: 10))
                                    .foregroundColor(SRColor.textSecond)
                            }
                        }

                        // Progress bar
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(SRColor.border)
                                    .frame(height: 5)
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(candidate.porcentaje >= 80 ? SRColor.srGreen : SRColor.brand)
                                    .frame(width: geo.size.width * min(candidate.porcentaje / 100, 1), height: 5)
                            }
                        }
                        .frame(height: 5)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                }
                .background(SRColor.cardBg)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(SRColor.border, lineWidth: 1)
                )

            } else {
                // Idle state card
                HStack(spacing: 10) {
                    queryStatusView
                    Spacer()
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(SRColor.cardBg)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(SRColor.border, lineWidth: 1)
                )
            }
        }
    }

    @ViewBuilder
    private var queryStatusView: some View {
        switch acr.lastQueryStatus {
        case .querying:
            HStack(spacing: 8) {
                ProgressView().scaleEffect(0.65).tint(SRColor.brand)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Identificando canción…")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(SRColor.textPrimary)
                    Text("Analizando audio del sistema")
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textSecond)
                }
            }
        case .matched(let s):
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(SRColor.srGreen).font(.system(size: 16))
                VStack(alignment: .leading, spacing: 1) {
                    Text("Reconocida").font(.system(size: 10)).foregroundColor(SRColor.textSecond)
                    Text(s).font(.system(size: 12, weight: .semibold)).foregroundColor(SRColor.textPrimary).lineLimit(1)
                }
            }
        case .matchedOutOfCatalog(let s):
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.circle").foregroundColor(SRColor.venueOrange).font(.system(size: 16))
                VStack(alignment: .leading, spacing: 1) {
                    Text("Fuera del catálogo SumarteRed").font(.system(size: 10)).foregroundColor(SRColor.venueOrange)
                    Text(s).font(.system(size: 12, weight: .semibold)).foregroundColor(SRColor.textPrimary).lineLimit(1)
                }
            }
        case .noFpcalc:
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundColor(SRColor.venueOrange).font(.system(size: 16))
                VStack(alignment: .leading, spacing: 1) {
                    Text("fpcalc no instalado").font(.system(size: 12, weight: .medium)).foregroundColor(SRColor.venueOrange)
                    Text("brew install chromaprint").font(.system(size: 10, design: .monospaced)).foregroundColor(SRColor.textSecond)
                }
            }
        case .notConfigured:
            HStack(spacing: 8) {
                Image(systemName: "key.slash").foregroundColor(SRColor.venueOrange).font(.system(size: 16))
                Text("Venue no configurado").font(.system(size: 12)).foregroundColor(SRColor.venueOrange)
            }
        default:
            HStack(spacing: 8) {
                ZStack {
                    Circle()
                        .fill(SRColor.pageBg)
                        .frame(width: 32, height: 32)
                    Image(systemName: "pause.circle")
                        .font(.system(size: 16))
                        .foregroundColor(SRColor.border)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("Sin reproducción activa")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(SRColor.textSecond)
                    Text("Esperando audio del sistema…")
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textLabel)
                }
            }
        }
    }

    // MARK: - Settings Inline
    private var settingsInline: some View {
        settingsView
    }

    // MARK: - Settings Content
    private var settingsView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {

                // ── Venue ──────────────────────────────────────────────
                settingsSection(title: "Venue") {
                    settingsStackRow(label: "ID", value: config.config.venueId)
                    Divider().overlay(SRColor.border).padding(.leading, 16)
                    settingsRow(label: "Nombre", value: config.config.nombreLocal.isEmpty ? "—" : config.config.nombreLocal)
                    Divider().overlay(SRColor.border).padding(.leading, 16)
                    settingsStackRow(label: "Servidor", value: config.config.serverURL)
                    Divider().overlay(SRColor.border).padding(.leading, 16)
                    settingsRow(label: "API Key",
                                value: config.config.apiKey.isEmpty ? "—" :
                                       "••••••••" + config.config.apiKey.suffix(6))
                }

                // ── Reconocimiento Acústico ───────────────────────────
                settingsSection(title: "Reconocimiento Acústico") {
                    // Audio capture
                    HStack(spacing: 10) {
                        Image(systemName: audio.isCapturing
                              ? "waveform" : audio.needsRestart ? "arrow.clockwise.circle" : "waveform.slash")
                            .foregroundColor(audio.isCapturing ? SRColor.srGreen
                                             : audio.needsRestart ? SRColor.venueOrange : SRColor.textSecond)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Captura de audio del sistema").font(.system(size: 13))
                                .foregroundColor(SRColor.textPrimary)
                            Text(audio.isCapturing ? "Activa — loopback del sistema"
                                                   : permissionLabel)
                                .font(.system(size: 10))
                                .foregroundColor(audio.isCapturing ? SRColor.srGreen : SRColor.venueOrange)
                        }
                        Spacer()
                        if audio.needsRestart {
                            Button("Reiniciar app") { audio.relaunchApp() }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(SRColor.venueOrange)
                        } else if audio.permissionStatus == .unknown {
                            Button("Activar") { audio.requestPermissionAndStart() }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(SRColor.brand)
                        } else if audio.permissionStatus == .denied {
                            Button("Abrir Ajustes") { audio.openPrivacySettings() }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(SRColor.brand)
                            Button("Reintentar") { audio.requestPermissionAndStart() }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(SRColor.textSecond)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 9)

                    Divider().overlay(SRColor.border).padding(.leading, 16)

                    // Catalog
                    HStack(spacing: 10) {
                        let catOk = catalog.catalogCount > 0
                        Image(systemName: catOk ? "music.note.list" : "arrow.triangle.2.circlepath")
                            .foregroundColor(catOk ? SRColor.srGreen : SRColor.venueOrange)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Catálogo local").font(.system(size: 13)).foregroundColor(SRColor.textPrimary)
                            Text(catalogStatusLabel).font(.system(size: 10))
                                .foregroundColor(catOk ? SRColor.textSecond : SRColor.venueOrange)
                        }
                        Spacer()
                        if !catOk {
                            Button("Descargar") { Task { await CatalogManager.shared.downloadFull() } }
                                .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(SRColor.brand)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 9)

                    Divider().overlay(SRColor.border).padding(.leading, 16)

                    // fpcalc
                    HStack(spacing: 10) {
                        Image(systemName: FingerprintEngine.isAvailable ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundColor(FingerprintEngine.isAvailable ? SRColor.srGreen : SRColor.venueOrange)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("fpcalc (Chromaprint)").font(.system(size: 13)).foregroundColor(SRColor.textPrimary)
                            Text(FingerprintEngine.isAvailable
                                 ? FingerprintEngine.fpcalcPath ?? ""
                                 : "No instalado — brew install chromaprint")
                                .font(.system(size: 10))
                                .foregroundColor(FingerprintEngine.isAvailable ? SRColor.textSecond : SRColor.venueOrange)
                                .lineLimit(1)
                        }
                        Spacer()
                        if !FingerprintEngine.isAvailable {
                            Button("Instalar") {
                                NSWorkspace.shared.open(URL(string: "https://formulae.brew.sh/formula/chromaprint")!)
                            }
                            .font(.system(size: 11)).buttonStyle(.plain).foregroundColor(SRColor.brand)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 9)
                }

                // ── Detección ─────────────────────────────────────────
                settingsSection(title: "Detección") {
                    settingsRow(label: "Tiempo mínimo",
                                value: "\(String(format: "%.0f", config.config.minDetectionTime))s")
                    Divider().overlay(SRColor.border).padding(.leading, 16)
                    settingsRow(label: "Umbral efectivo",
                                value: "\(String(format: "%.0f", config.config.umbralPorcentaje))%")
                    Divider().overlay(SRColor.border).padding(.leading, 16)
                    settingsRow(label: "Confianza mínima",
                                value: "\(String(format: "%.0f", config.config.scoreThreshold * 100))%")
                    Divider().overlay(SRColor.border).padding(.leading, 16)
                    settingsRow(label: "Tarifa por play",
                                value: "\(String(format: "%.0f", config.config.tarifaPlay)) COP")
                }

                // ── Sistema ───────────────────────────────────────────
                settingsSection(title: "Sistema") {
                    HStack {
                        Text("Iniciar con el sistema")
                            .font(.system(size: 13))
                            .foregroundColor(SRColor.textPrimary)
                        Spacer()
                        Toggle("", isOn: Binding(
                            get: { config.config.launchAtLogin },
                            set: { newVal in
                                config.config.launchAtLogin = newVal
                                LaunchAtLoginManager.setEnabled(newVal)
                            }
                        )).labelsHidden().tint(SRColor.brand)
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
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 16).padding(.vertical, 14)
            }
            .padding(.vertical, 8)
        }
        .background(SRColor.pageBg)
    }

    // MARK: - Helpers
    private var catalogStatusLabel: String {
        switch catalog.syncStatus {
        case .downloading(let n): return n > 0 ? "Descargando… \(n) recibidos" : "Descargando catálogo…"
        case .checking:           return "Verificando actualizaciones…"
        case .error(let msg):     return "Error: \(msg)"
        default:
            let count = catalog.catalogCount
            return count > 0 ? "\(count) tracks en catálogo" : "Sin catálogo — descarga pendiente"
        }
    }

    private var permissionLabel: String {
        if audio.needsRestart { return "Permiso otorgado — reinicia la app para activar" }
        switch audio.permissionStatus {
        case .unknown:  return "Permiso no solicitado aún"
        case .denied:   return "Sin permiso — Ajustes → Privacidad → Grabación de pantalla"
        case .granted:  return "Concedido"
        }
    }

    private func settingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(SRColor.textLabel)
                .kerning(0.3)
                .padding(.horizontal, 16)
                .padding(.top, 14)
                .padding(.bottom, 6)
            VStack(spacing: 0) { content() }
                .background(SRColor.cardBg)
                .cornerRadius(8)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(SRColor.border, lineWidth: 1))
                .padding(.horizontal, 16)
        }
    }

    private func settingsRow(label: String, value: String) -> some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.system(size: 13))
                .foregroundColor(SRColor.textPrimary)
                .frame(width: 120, alignment: .leading)
            Text(value)
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(SRColor.textSecond)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
    }

    private func settingsStackRow(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 13)).foregroundColor(SRColor.textPrimary)
            Text(value.isEmpty ? "—" : value)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(SRColor.textSecond)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16).padding(.vertical, 10)
    }

    private func loadHistory() {
        history      = DatabaseManager.shared.fetchHistory(limit: 200)
        pendingCount = DatabaseManager.shared.countPending()
    }

    private func startRefresh() {
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
            loadHistory()
        }
    }
}

#Preview { ContentView() }
