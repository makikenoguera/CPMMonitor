import SwiftUI

// MARK: - Modelo de respuesta del servidor
struct PromovidaRemota: Identifiable, Decodable {
    let id: String
    let artistaNombre: String
    let titulo: String
    let isrc: String
    let genero: String
    let creditosTotal: Int
    let creditosUsados: Int
    let tarifaVenue: Double
    let activa: Bool
    let fechaInicio: String?
    let fechaFin: String?
    let linkSpotify: String
    let linkYoutube: String

    enum CodingKeys: String, CodingKey {
        case id
        case artistaNombre  = "artista_nombre"
        case titulo, isrc, genero
        case creditosTotal  = "creditos_total"
        case creditosUsados = "creditos_usados"
        case tarifaVenue    = "tarifa_venue"
        case activa
        case fechaInicio    = "fecha_inicio"
        case fechaFin       = "fecha_fin"
        case linkSpotify    = "link_spotify"
        case linkYoutube    = "link_youtube"
    }
}

// MARK: - Vista
struct PromovidasView: View {
    @StateObject private var config = ConfigManager.shared

    @State private var rows: [PromovidaRemota] = []
    @State private var isLoading = false
    @State private var errorMsg: String? = nil

    var body: some View {
        Group {
            if isLoading {
                VStack(spacing: 10) {
                    ProgressView().scaleEffect(0.8)
                    Text("Cargando promovidas…")
                        .font(.caption).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            } else if let err = errorMsg {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 30)).foregroundColor(SRColor.srGreen.opacity(0.7))
                    Text("No se pudo cargar").font(.subheadline).foregroundColor(.secondary)
                    Text(err).font(.caption2).foregroundColor(.secondary.opacity(0.6))
                        .multilineTextAlignment(.center).padding(.horizontal, 24)
                    Button("Reintentar") { load() }
                        .font(.caption).buttonStyle(.plain).foregroundColor(SRColor.brand)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.top, 30)

            } else if rows.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "star.slash")
                        .font(.system(size: 36)).foregroundColor(.secondary.opacity(0.35))
                    Text("Sin canciones promovidas")
                        .font(.subheadline).foregroundColor(.secondary)
                    Text("Agrega canciones en el panel de administración:\nmonitor.sumartered.com")
                        .font(.caption).foregroundColor(.secondary.opacity(0.7))
                        .multilineTextAlignment(.center).padding(.horizontal, 32)
                    Button("Abrir dashboard") {
                        if let url = URL(string: "\(config.config.serverURL)/dashboard") {
                            NSWorkspace.shared.open(url)
                        }
                    }
                    .font(.caption).buttonStyle(.plain).foregroundColor(SRColor.brand)
                    .padding(.top, 4)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.top, 30)

            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        HStack {
                            Label("\(rows.count) canciones promovidas activas", systemImage: "star.fill")
                                .font(.caption.weight(.semibold)).foregroundColor(SRColor.srGreen)
                            Spacer()
                            Button { load() } label: {
                                Image(systemName: "arrow.clockwise")
                                    .font(.caption).foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 8)

                        Divider().padding(.horizontal, 16)

                        ForEach(rows) { row in
                            promoRow(row)
                            Divider().padding(.horizontal, 16).opacity(0.4)
                        }
                    }
                }
            }
        }
        .onAppear { load() }
    }

    // MARK: - Row
    private func promoRow(_ row: PromovidaRemota) -> some View {
        HStack(spacing: 10) {
            ZStack {
                Circle().fill(SRColor.srGreen.opacity(0.12)).frame(width: 34, height: 34)
                Image(systemName: "music.note")
                    .font(.system(size: 14, weight: .semibold)).foregroundColor(SRColor.srGreen)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(row.titulo)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.primary).lineLimit(1)
                HStack(spacing: 5) {
                    Text(row.artistaNombre)
                        .font(.system(size: 11)).foregroundColor(.secondary).lineLimit(1)
                    if !row.isrc.isEmpty {
                        Text("·").foregroundColor(.secondary.opacity(0.4))
                        Text(row.isrc)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.secondary.opacity(0.65))
                    }
                    if !row.genero.isEmpty {
                        Text("·").foregroundColor(.secondary.opacity(0.4))
                        Text(row.genero)
                            .font(.system(size: 10)).foregroundColor(.secondary.opacity(0.65))
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Links Spotify / YouTube
            HStack(spacing: 6) {
                if !row.linkSpotify.isEmpty, let url = URL(string: row.linkSpotify) {
                    Link(destination: url) {
                        Text("Spotify")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(Color(red: 0.11, green: 0.73, blue: 0.33))
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .background(Color(red: 0.11, green: 0.73, blue: 0.33).opacity(0.12))
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                    .help("Abrir en Spotify")
                }
                if !row.linkYoutube.isEmpty, let url = URL(string: row.linkYoutube) {
                    Link(destination: url) {
                        Text("YT")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(Color(red: 0.86, green: 0.07, blue: 0.07))
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .background(Color(red: 0.86, green: 0.07, blue: 0.07).opacity(0.12))
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                    .help("Abrir en YouTube")
                }
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
    }

    // MARK: - Carga desde servidor
    private func load() {
        guard !config.config.serverURL.isEmpty else {
            errorMsg = "Servidor no configurado"
            return
        }
        let urlStr = "\(config.config.serverURL)/v1/promovidas"
        guard let url = URL(string: urlStr) else { return }

        isLoading = true
        errorMsg = nil

        var req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        if !config.config.apiKey.isEmpty {
            req.setValue(config.config.apiKey, forHTTPHeaderField: "X-API-Key")
        }

        URLSession.shared.dataTask(with: req) { data, resp, err in
            DispatchQueue.main.async {
                isLoading = false
                if let err = err {
                    errorMsg = err.localizedDescription
                    return
                }
                guard let data = data else { errorMsg = "Sin datos"; return }
                do {
                    let all = try JSONDecoder().decode([PromovidaRemota].self, from: data)
                    rows = all.filter { $0.activa }
                } catch {
                    errorMsg = "Error al leer respuesta"
                    print("[PromovidasView] decode error: \(error)")
                }
            }
        }.resume()
    }
}
